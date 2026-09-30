import json
import os
import subprocess
import sys
import urllib.request

from ..controller import run_controller
from ..controller.types import ControllerConfig
from ..env import get_env, get_env_int


def handle_control(args) -> None:
    cfg = ControllerConfig(
        host=args.host or get_env("WHAT_CONTROL_HOST") or "127.0.0.1",
        port=args.port or get_env_int("WHAT_CONTROL_PORT") or 8780,
        service_host=args.service_host or get_env("WHAT_SERVICE_HOST") or "127.0.0.1",
        service_port=args.service_port or get_env_int("WHAT_SERVICE_PORT") or 8765,
        config_path=args.config or get_env("WHAT_CONFIG"),
        settings_path=args.settings_path or get_env("WHAT_CONTROL_SETTINGS"),
    )
    status = _controller_status(cfg.host, cfg.port)
    if status is not None:
        if "stream_running" in status:
            sys.stderr.write(f"control: reusing running controller at {cfg.host}:{cfg.port}\n")
            return
        sys.stderr.write(
            f"control: legacy controller detected at {cfg.host}:{cfg.port}; replacing it\n"
        )
        _kill_listener_on_port(cfg.port)
    run_controller(cfg)


def _controller_running(host: str, port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/control/status", timeout=0.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def _controller_status(host: str, port: int) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/control/status", timeout=0.8) as resp:
            if resp.status != 200:
                return None
            payload = json.loads(resp.read().decode("utf-8"))
            return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _kill_listener_on_port(port: int) -> None:
    try:
        out = subprocess.check_output(
            ["lsof", "-ti", f"tcp:{int(port)}"], stderr=subprocess.DEVNULL, text=True
        ).strip()
    except Exception:
        return
    if not out:
        return
    for raw in out.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            os.kill(int(raw), 15)
        except Exception:
            continue
