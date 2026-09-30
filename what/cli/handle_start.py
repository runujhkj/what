import asyncio
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

from .builders import build_audio_cfg, build_input_cfg
from ..client import ClientConfig, run_client
from ..env import get_env, get_env_int
from ..pair import request_pair_token


def handle_start(args, cfg: dict) -> None:
    service_host = args.service_host or get_env("WHAT_SERVICE_HOST") or "127.0.0.1"
    service_port = args.service_port or get_env_int("WHAT_SERVICE_PORT") or cfg["service"]["port"]
    connect_host = "127.0.0.1" if service_host == "0.0.0.0" else service_host

    controller_applied = _try_apply_via_controller(args, cfg, service_host, service_port)
    proc = None
    service_healthy = _is_service_healthy(connect_host, service_port)
    if controller_applied:
        sys.stderr.write(
            f"start: reusing controller-managed service at {connect_host}:{service_port}\n"
        )
        _wait_for_service(connect_host, service_port, args.health_timeout)
        service_healthy = True
    elif service_healthy and _service_overrides_present(args):
        alt_port = _find_open_port(start_from=int(service_port) + 1)
        sys.stderr.write(
            "start: existing unmanaged service is running; "
            f"starting fresh service with requested settings on {connect_host}:{alt_port}\n"
        )
        service_port = alt_port
        connect_host = "127.0.0.1" if service_host == "0.0.0.0" else service_host
        proc = _start_service_process(args, service_host, service_port)
        service_healthy = False

    if service_healthy and args.force_service:
        raise RuntimeError(
            f"service already running at {connect_host}:{service_port}; "
            "stop it first or use a different --service-port"
        )
    if service_healthy and not controller_applied:
        sys.stderr.write(
            f"start: reusing running service at {connect_host}:{service_port}\n"
        )
    elif not service_healthy and proc is None and not controller_applied:
        proc = _start_service_process(args, service_host, service_port)
    try:
        _wait_for_service(connect_host, service_port, args.health_timeout)
        token = request_pair_token("", connect_host, service_port, cfg["service"]["pair_path"])
        audio_cfg = build_audio_cfg(args, cfg)
        input_cfg = build_input_cfg(args, cfg)
        client_cfg = ClientConfig(
            transport=cfg["client"]["transport"],
            target_host=connect_host,
            target_port=service_port,
            target_ws_path=cfg["client"]["target_ws_path"],
            target_sse_path=cfg["client"]["target_sse_path"],
        )
        asyncio.run(
            run_client(
                client_cfg=client_cfg,
                input_cfg=input_cfg,
                audio_cfg=audio_cfg,
                token=token,
                client_name=get_env("WHAT_CLIENT_ID"),
                captions_on=True,
                captions_mode=cfg["output"].get("text_mode", "delta"),
                captions_block_clear=cfg["output"].get("text_block_clear", False),
                captions_normalize=cfg["output"].get("text_normalize", False),
                transcript_prefix=args.transcript_prefix,
                event_prefix=args.event_prefix,
            )
        )
    except KeyboardInterrupt:
        sys.stderr.write("^C\nstart stopped\n")
    finally:
        _stop_service_process(proc)


def _start_service_process(args, host: str, port: int) -> subprocess.Popen:
    cmd = [sys.executable, "-m", "what", "service"]
    if args.config:
        cmd += ["--config", args.config]
    if args.preset:
        cmd += ["--preset", args.preset]
    if args.profile:
        cmd += ["--profile", args.profile]
    if args.model:
        cmd += ["--model", args.model]
    if args.compute_type:
        cmd += ["--compute-type", args.compute_type]
    if args.beam_size is not None:
        cmd += ["--beam-size", str(args.beam_size)]
    if args.lang:
        cmd += ["--lang", args.lang]
    if args.device:
        cmd += ["--device", args.device]
    if args.device_index is not None:
        cmd += ["--device-index", str(args.device_index)]
    cmd += ["--host", host, "--port", str(port)]
    return subprocess.Popen(cmd, stdout=sys.stdout, stderr=sys.stderr)


def _wait_for_service(host: str, port: int, timeout_s: float) -> None:
    deadline = time.time() + max(timeout_s, 1.0)
    url = f"http://{host}:{port}/health"
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:
            last_err = exc
            time.sleep(0.2)
    raise RuntimeError(f"service did not become healthy: {last_err}")


def _is_service_healthy(host: str, port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/health", timeout=0.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def _service_overrides_present(args) -> bool:
    return any(
        [
            bool(args.profile),
            bool(args.model),
            bool(args.compute_type),
            args.beam_size is not None,
            bool(args.lang),
            bool(args.device),
            args.device_index is not None,
            args.no_speech_threshold is not None,
            args.logprob_threshold is not None,
            args.compression_ratio_threshold is not None,
            bool(args.condition_on_previous_text),
            args.chunk_ms is not None,
            args.overlap_ms is not None,
            args.frame_ms is not None,
            bool(args.no_vad),
            args.vad_mode is not None,
            args.vad_speech_ratio is not None,
        ]
    )


def _find_open_port(start_from: int) -> int:
    port = max(1024, start_from)
    for _ in range(200):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                port += 1
    raise RuntimeError("could not find open local port for start service")


def _controller_status() -> dict | None:
    base = get_env("WHAT_CONTROL_URL") or "http://127.0.0.1:8780"
    url = f"{base}/control/status"
    try:
        with urllib.request.urlopen(url, timeout=0.5) as resp:
            if resp.status != 200:
                return None
            payload = json.loads(resp.read().decode("ascii"))
            return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _controller_apply(payload: dict) -> bool:
    base = get_env("WHAT_CONTROL_URL") or "http://127.0.0.1:8780"
    url = f"{base}/control/apply"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("ascii"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            return resp.status == 200
    except urllib.error.URLError:
        return False
    except Exception:
        return False


def _try_apply_via_controller(args, cfg: dict, service_host: str, service_port: int) -> bool:
    status = _controller_status()
    if not status:
        return False
    status_host = status.get("service_host")
    status_port = int(status.get("service_port", 0) or 0)
    if status_host != service_host or status_port != int(service_port):
        return False
    payload: dict[str, object] = {}
    if args.profile:
        payload["profile"] = args.profile
    if args.device:
        payload["device"] = args.device
    if args.device_index is not None:
        payload["device_index"] = int(args.device_index)
    if args.compute_type:
        payload["compute_type"] = args.compute_type
    if args.model:
        payload["model_size"] = args.model
    if args.beam_size is not None:
        payload["beam_size"] = int(args.beam_size)
    if args.lang:
        payload["language"] = args.lang
    if "publish_delay_seconds" in cfg.get("output", {}):
        payload["publish_delay_seconds"] = int(cfg["output"]["publish_delay_seconds"])
    return _controller_apply(payload)


def _stop_service_process(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except Exception:
        proc.kill()
