from __future__ import annotations

import json
from pathlib import Path
from threading import Thread
import time
import urllib.request

from fastapi import HTTPException

from ..cli.helpers import make_session_label
from ..config import load_config
from ..env import get_env


def append_stream_log(state, line: str, *, count_for_heartbeat: bool = True) -> None:
    text = str(line).rstrip("\n")
    now = time.time()
    with state.stream_log_lock:
        state.stream_log_seq += 1
        state.stream_logs.append((state.stream_log_seq, text))
        if count_for_heartbeat:
            state.stream_log_last_ts = now
        if state.process_log_handle is not None:
            stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
            state.process_log_handle.write(f"{stamp} {text}\n")
            state.process_log_handle.flush()


def start_stream_log_pump(state, proc, append_log) -> None:
    def _pump(pipe, label: str) -> None:
        if pipe is None:
            return
        try:
            for raw in iter(pipe.readline, ""):
                line = raw.rstrip("\n")
                if not line:
                    continue
                append_log(state, line)
        except Exception:
            append_log(state, f"{label} log pump stopped")

    Thread(target=_pump, args=(getattr(proc, "stdout", None), "stdout"), daemon=True).start()
    Thread(target=_pump, args=(getattr(proc, "stderr", None), "stderr"), daemon=True).start()


def wait_for_service_health(host: str, port: int, timeout_s: float) -> None:
    target_host = "127.0.0.1" if host == "0.0.0.0" else host
    deadline = time.time() + max(1.0, timeout_s)
    url = f"http://{target_host}:{port}/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.6) as resp:
                if resp.status == 200:
                    return
        except Exception:
            time.sleep(0.15)
    raise HTTPException(status_code=503, detail="service not ready")


def read_service_health(host: str, port: int) -> dict[str, object]:
    target_host = "127.0.0.1" if host == "0.0.0.0" else host
    url = f"http://{target_host}:{port}/health"
    with urllib.request.urlopen(url, timeout=1.0) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload if isinstance(payload, dict) else {}


def resolve_log_root(cfg, repo_root: Path) -> Path:
    # WHAT_JSONL_DIR (an absolute, writable dir) wins so a packaged app does not try to
    # write session logs under its read-only bundled source. Matches build_output_cfg.
    env_dir = get_env("WHAT_JSONL_DIR")
    if env_dir:
        return Path(env_dir)
    config = load_config(cfg.config_path)
    raw = str(config.get("output", {}).get("jsonl_dir", "logs") or "logs")
    path = Path(raw)
    if not path.is_absolute():
        path = repo_root / path
    return path


def close_process_log(state, clear_session: bool) -> None:
    handle = state.process_log_handle
    state.process_log_handle = None
    state.process_log_path = None
    if clear_session:
        state.current_session_id = None
    if handle is not None:
        try:
            handle.close()
        except Exception:
            pass


def ensure_process_session(
    *,
    cfg,
    state,
    repo_root: Path,
    process_running,
    append_log,
    read_service_health_fn=read_service_health,
    resolve_log_root_fn=resolve_log_root,
) -> str:
    if state.current_session_id and state.process_log_handle is not None and state.process_log_path:
        return state.current_session_id
    try:
        session_id = state.current_session_id or ""
        if not session_id and process_running(state.process):
            health = read_service_health_fn(cfg.service_host, cfg.service_port)
            session_id = str(health.get("session_id") or "").strip()
        if not session_id:
            session_id = make_session_label(str(resolve_log_root_fn(cfg, repo_root)))
        session_dir = resolve_log_root_fn(cfg, repo_root) / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        process_log_path = str(session_dir / "process.log")
        if state.process_log_path == process_log_path and state.process_log_handle is not None:
            state.current_session_id = session_id
            return session_id
        close_process_log(state, clear_session=False)
        state.process_log_handle = open(process_log_path, "a", encoding="utf-8")
        state.process_log_path = process_log_path
        state.current_session_id = session_id
        append_log(state, f"process log attached: {process_log_path}")
        return session_id
    except Exception as exc:
        append_log(state, f"process log attach failed: {exc}")
        return state.current_session_id or ""
