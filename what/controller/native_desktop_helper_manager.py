from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from .native_desktop_backend import (
    desktop_source_backend,
    native_helper_path,
    native_helper_ready,
    native_helper_supported,
)


RECEIPT_FILE = "native_desktop_helper_receipt.json"


def _receipt_path(state_dir: Path) -> Path:
    return Path(state_dir) / RECEIPT_FILE


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _remove_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def _pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _terminate_pid(pid: int) -> bool:
    if not _pid_running(pid):
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except Exception:
        return False
    deadline = time.time() + 2.0
    while time.time() < deadline:
        if not _pid_running(pid):
            return True
        time.sleep(0.05)
    try:
        os.kill(pid, signal.SIGKILL)
    except Exception:
        return False
    deadline = time.time() + 1.0
    while time.time() < deadline:
        if not _pid_running(pid):
            return True
        time.sleep(0.05)
    return not _pid_running(pid)


def _health_check(url: str, timeout_s: float = 0.5) -> tuple[bool, int, dict]:
    if not str(url or "").strip():
        return False, 0, {}
    try:
        with urllib.request.urlopen(url, timeout=max(0.1, float(timeout_s))) as resp:
            data = resp.read()
            payload = {}
            try:
                parsed = json.loads(data.decode("utf-8"))
                if isinstance(parsed, dict):
                    payload = parsed
            except Exception:
                payload = {}
            return bool(resp.status == 200), int(resp.status), payload
    except Exception:
        return False, 0, {}


def _helper_command(
    *,
    session_id: str,
    service_host: str,
    service_port: int,
    health_port: int,
    ws_path: str,
    pair_path: str,
    capture_mode: str,
    desktop_device: str,
    no_stream: bool,
) -> list[str]:
    override = str(os.environ.get("WHAT_DESKTOP_NATIVE_HELPER_CMD", "")).strip()
    if override:
        # Intentional simple split for fixed local dev command usage.
        return override.split()
    # Default to the same interpreter env as controller so module deps
    # (e.g. websockets) match runtime expectations.
    cmd = [
        str(sys.executable),
        "-m",
        "what.native_desktop_helper",
        "--session-id",
        str(session_id or ""),
        "--service-host",
        str(service_host or "127.0.0.1"),
        "--service-port",
        str(int(service_port)),
        "--ws-path",
        str(ws_path or "/ingest"),
        "--pair-path",
        str(pair_path or "/pair"),
        "--health-port",
        str(int(health_port)),
        "--capture-mode",
        str(capture_mode or "tone"),
        "--desktop-device",
        str(desktop_device or ""),
    ]
    if bool(no_stream):
        cmd.append("--no-stream")
    return cmd


def _pick_health_port(preferred: int) -> int:
    target = int(preferred or 0)
    if target > 0:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("127.0.0.1", target))
            return target
        except OSError:
            pass
        finally:
            try:
                sock.close()
            except Exception:
                pass
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        try:
            sock.close()
        except Exception:
            pass


def get_status(state_dir: Path) -> dict[str, object]:
    state_dir = Path(state_dir)
    receipt = _read_json(_receipt_path(state_dir))
    pid = int(receipt.get("pid") or 0)
    health_url = str(receipt.get("health_url") or "").strip()
    running = _pid_running(pid)
    health_ok, health_status, health_payload = _health_check(health_url) if running else (False, 0, {})
    return {
        "supported": bool(native_helper_supported()),
        "backend": desktop_source_backend(),
        "helper_path": str(native_helper_path()),
        "helper_ready": bool(native_helper_ready()),
        "running": bool(running),
        "pid": int(pid),
        "health_url": health_url,
        "health_ok": bool(health_ok),
        "health_status": int(health_status),
        "health_payload": health_payload if isinstance(health_payload, dict) else {},
        "capture_mode": str(receipt.get("capture_mode") or ""),
        "desktop_device": str(receipt.get("desktop_device") or ""),
        "no_stream": bool(receipt.get("no_stream", False)),
        "state_dir": str(state_dir),
        "receipt_path": str(_receipt_path(state_dir)),
        "last_error": str(receipt.get("last_error") or ""),
    }


def start(
    *,
    state_dir: Path,
    session_id: str,
    service_host: str,
    service_port: int,
    ws_path: str = "/ingest",
    pair_path: str = "/pair",
    capture_mode: str = "tone",
    desktop_device: str = "",
    health_port: int = 8793,
    no_stream: bool = False,
) -> dict[str, object]:
    state_dir = Path(state_dir)
    receipt_path = _receipt_path(state_dir)
    status_before = get_status(state_dir)
    if not native_helper_supported():
        return {"ok": False, "error": "unsupported_platform", "status": status_before}
    if not native_helper_ready():
        return {"ok": False, "error": "native_helper_not_ready", "status": status_before}
    if status_before.get("running"):
        current = _read_json(receipt_path)
        current_mode = str(current.get("capture_mode") or "")
        current_device = str(current.get("desktop_device") or "")
        current_no_stream = bool(current.get("no_stream", False))
        desired_matches = (
            current_mode == str(capture_mode or "")
            and current_device == str(desktop_device or "")
            and current_no_stream == bool(no_stream)
        )
        # Healthy helper is idempotent; unhealthy running helper is stale and
        # should be recycled before launching a new one.
        if bool(status_before.get("health_ok")) and desired_matches:
            return {"ok": True, "changed": False, "status": status_before}
        stale_pid = int(status_before.get("pid") or 0)
        if stale_pid > 0:
            _terminate_pid(stale_pid)
        _remove_file(receipt_path)
        status_before = get_status(state_dir)

    selected_health_port = _pick_health_port(health_port)
    cmd = _helper_command(
        session_id=session_id,
        service_host=service_host,
        service_port=service_port,
        health_port=selected_health_port,
        ws_path=ws_path,
        pair_path=pair_path,
        capture_mode=capture_mode,
        desktop_device=desktop_device,
        no_stream=no_stream,
    )
    health_url = f"http://127.0.0.1:{int(selected_health_port)}/health"
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            cwd=str(Path(__file__).resolve().parents[2]),
        )
    except Exception as exc:
        _write_json(
            receipt_path,
            {
                "last_error": f"launch_failed: {exc}",
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        )
        return {"ok": False, "error": "launch_failed", "detail": str(exc), "status": get_status(state_dir)}

    _write_json(
        receipt_path,
        {
            "pid": int(proc.pid),
            "health_url": health_url,
            "session_id": str(session_id or ""),
            "service_host": str(service_host or ""),
            "service_port": int(service_port),
            "health_port": int(selected_health_port),
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "capture_mode": str(capture_mode or ""),
            "desktop_device": str(desktop_device or ""),
            "no_stream": bool(no_stream),
            "cmd": cmd,
            "last_error": "",
        },
    )
    timeout_s = float(os.environ.get("WHAT_DESKTOP_NATIVE_HELPER_START_TIMEOUT_SEC", "2.0") or "2.0")
    deadline = time.time() + max(0.2, timeout_s)
    while time.time() < deadline:
        if not _pid_running(int(proc.pid)):
            _write_json(
                receipt_path,
                {
                    "pid": int(proc.pid),
                    "health_url": health_url,
                    "last_error": "exited_early",
                    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                },
            )
            return {"ok": False, "error": "exited_early", "status": get_status(state_dir)}
        ok, _status_code, _payload = _health_check(health_url, timeout_s=0.25)
        if ok:
            return {"ok": True, "changed": True, "status": get_status(state_dir)}
        time.sleep(0.06)
    if not _pid_running(int(proc.pid)):
        _write_json(
            receipt_path,
            {
                "pid": int(proc.pid),
                "health_url": health_url,
                "last_error": "exited_during_health_wait",
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        )
        return {"ok": False, "error": "exited_during_health_wait", "status": get_status(state_dir)}
    _write_json(
        receipt_path,
        {
            "pid": int(proc.pid),
            "health_url": health_url,
            "last_error": "health_timeout",
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        },
    )
    return {"ok": False, "error": "health_timeout", "status": get_status(state_dir)}


def stop(*, state_dir: Path) -> dict[str, object]:
    state_dir = Path(state_dir)
    receipt_path = _receipt_path(state_dir)
    receipt = _read_json(receipt_path)
    pid = int(receipt.get("pid") or 0)
    if pid <= 0:
        _remove_file(receipt_path)
        return {"ok": True, "changed": False, "status": get_status(state_dir)}
    changed = _terminate_pid(pid)
    if changed:
        _remove_file(receipt_path)
        return {"ok": True, "changed": True, "status": get_status(state_dir)}
    status_after = get_status(state_dir)
    if (not bool(status_after.get("running"))) or (not bool(status_after.get("health_ok"))):
        _remove_file(receipt_path)
        return {"ok": True, "changed": True, "status": get_status(state_dir)}
    return {"ok": False, "error": "stop_failed", "status": status_after}
