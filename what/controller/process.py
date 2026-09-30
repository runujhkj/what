import subprocess
import sys
import os
import errno
import socket

from fastapi import HTTPException
from pathlib import Path

from .state import ControlSettings, StreamSettings
from .types import ControllerConfig

REPO_ROOT = Path(__file__).resolve().parents[2]


def build_service_args(cfg: ControllerConfig, settings: ControlSettings) -> list[str]:
    args = [sys.executable, "-m", "what", "service"]
    if bool(settings.no_vad):
        args += ["--no-vad"]
    if cfg.config_path:
        args += ["--config", cfg.config_path]
    if settings.profile:
        args += ["--profile", settings.profile]
    if settings.engine:
        args += ["--engine", settings.engine]
    if settings.device:
        args += ["--device", settings.device]
    if settings.device_index is not None:
        args += ["--device-index", str(settings.device_index)]
    if settings.compute_type:
        args += ["--compute-type", settings.compute_type]
    if settings.model_size:
        args += ["--model", settings.model_size]
    if settings.beam_size is not None:
        args += ["--beam-size", str(settings.beam_size)]
    if settings.language:
        args += ["--lang", settings.language]
    args += ["--boundary-candidate-points", str(max(1, min(7, int(settings.boundary_candidate_points or 3))))]
    args += ["--host", cfg.service_host, "--port", str(cfg.service_port)]
    return args


def build_service_env(settings: ControlSettings, base_env) -> dict[str, str]:
    env = dict(base_env)
    # A GUI budget overrides the launch environment; 0 leaves any WHAT_GPU_MEM_BUDGET_MB
    # the app was started with (e.g. from a shell) in effect.
    budget = int(getattr(settings, "gpu_mem_budget_mb", 0) or 0)
    if budget > 0:
        env["WHAT_GPU_MEM_BUDGET_MB"] = str(budget)
    return env


def start_service(cfg: ControllerConfig, settings: ControlSettings, session_id: str | None = None) -> subprocess.Popen:
    # Fail before loading a model or reporting success. Otherwise an unrelated
    # service's /health can satisfy GUI readiness after our child fails to bind.
    family = socket.AF_INET6 if ":" in cfg.service_host else socket.AF_INET
    try:
        with socket.socket(family, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind((cfg.service_host, cfg.service_port))
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            raise HTTPException(
                status_code=409,
                detail=f"Service port {cfg.service_host}:{cfg.service_port} is already in use. "
                       "Stop the existing service or choose another service port; "
                       "connecting to it could use another checkout's recordings.",
            ) from exc
        raise HTTPException(status_code=503, detail=f"Cannot bind service address: {exc}") from exc
    args = build_service_args(cfg, settings)
    env = build_service_env(settings, os.environ)
    if session_id:
        env["WHAT_SESSION_ID"] = session_id
    # A GUI-managed service must never read interactive fallback prompts from the
    # launch terminal. DEVNULL selects the service's existing automatic CPU fallback.
    return subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=sys.stdout,
                            stderr=sys.stderr, cwd=str(REPO_ROOT), env=env)


def build_client_args(cfg: ControllerConfig, settings: StreamSettings) -> list[str]:
    args = [sys.executable, "-m", "what", "client", "--local"]
    # Controller-managed streaming must always emit transcript/event output for
    # OBS/gui consumption, regardless of ambient WHAT_CAPTIONS_ON env value.
    args += ["--captions-on"]
    args += ["--host", cfg.service_host, "--port", str(cfg.service_port)]
    if settings.input_mode:
        args += ["--input", settings.input_mode]
    if settings.file_path:
        args += ["--file", settings.file_path]
    if settings.realtime:
        args += ["--realtime"]
    if settings.mic_enabled:
        args += ["--mic-enabled"]
    else:
        args += ["--no-mic"]
    if settings.mic_backend:
        args += ["--mic-backend", settings.mic_backend]
    if settings.mic_device:
        args += ["--mic-device", settings.mic_device]
    if settings.desktop_enabled:
        args += ["--desktop-enabled"]
    else:
        args += ["--no-desktop"]
    if settings.desktop_backend:
        args += ["--desktop-backend", settings.desktop_backend]
    desktop_capture_input = settings.desktop_capture_input or settings.desktop_device
    if desktop_capture_input:
        args += ["--desktop-device", desktop_capture_input]
    if settings.event_prefix:
        args += ["--event-prefix", settings.event_prefix]
    return args


def start_client(cfg: ControllerConfig, settings: StreamSettings) -> subprocess.Popen:
    args = build_client_args(cfg, settings)
    return subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        cwd=str(REPO_ROOT),
    )


def stop_client(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except Exception:
        proc.kill()


def stop_service(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except Exception:
        proc.kill()


def process_running(proc: subprocess.Popen | None) -> bool:
    return proc is not None and proc.poll() is None
