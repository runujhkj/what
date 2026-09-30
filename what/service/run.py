import os
import sys

import uvicorn

from ..asr import resolve_engine_name
from ..cli.helpers import make_session_label
from ..env import get_env
from .app import create_app
from .warmup import decode_preflight as _decode_preflight


def stdin_is_interactive(stdin=None, os_name=None, console_mode=None) -> bool:
    """True only when a person can answer a prompt on stdin.

    isatty() alone is wrong on Windows: it is True for the NUL device, which is what the
    GUI's controller gives the service (subprocess.DEVNULL). The service then took the
    interactive path there -- a synchronous model load before binding the port, and on a
    GPU failure an input() prompt that died on EOF. A real console also answers
    GetConsoleMode; NUL and pipes do not.
    """
    stdin = sys.stdin if stdin is None else stdin
    try:
        if stdin is None or not stdin.isatty():
            return False
    except (AttributeError, ValueError, OSError):
        return False
    if (os.name if os_name is None else os_name) != "nt":
        return True
    if console_mode is None:
        def console_mode(stream):
            import ctypes
            import msvcrt

            mode = ctypes.c_uint32()
            handle = msvcrt.get_osfhandle(stream.fileno())
            return bool(ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode)))
    try:
        return bool(console_mode(stdin))
    except (AttributeError, ValueError, OSError):
        return False


def _whisperkit_preflight(asr_cfg):
    """Fail at startup, with a WhisperKit-specific message, if the Metal model can't load.

    A CPU fallback is not offered: it would still select the WhisperKit engine, and the
    usual cause is a bad model cache rather than missing hardware support.
    """
    try:
        return _decode_preflight(asr_cfg)
    except Exception as exc:
        model = asr_cfg.model_path or asr_cfg.model_size
        sys.stderr.write(
            f"WhisperKit (Metal) model '{model}' failed to start: {exc}\n"
            "See the [worker] lines above. An incomplete Core ML download fails with "
            "'Error in reading the MIL network'; remove that model's folder under "
            "~/Library/Caches/what-whisperkit to re-download it, or select a model "
            "that has loaded successfully (the WhisperKit default is 'base').\n"
        )
        raise SystemExit(1)


def run_service(
    audio_cfg,
    vad_cfg,
    asr_cfg,
    output_cfg,
    service_cfg,
) -> None:
    spare_asr = None
    warm_in_background = False
    device_is_cuda = str(getattr(asr_cfg, "device", "")).lower().startswith("cuda")
    if resolve_engine_name(asr_cfg) == "whisperkit":
        spare_asr = _whisperkit_preflight(asr_cfg)
    elif device_is_cuda and stdin_is_interactive():
        # Interactive direct launch: keep the synchronous prompt path so a human at the
        # terminal still chooses whether to fall back to CPU.
        try:
            spare_asr = _decode_preflight(asr_cfg)
        except Exception as exc:
            sys.stderr.write(f"ASR init failed (CUDA check): {exc}\n")
            reply = input("CUDA/GPU not available, fall back to CPU? [y/N] ").strip().lower()
            if reply in {"y", "yes"}:
                asr_cfg.device = "cpu"
                if asr_cfg.compute_type not in {"int8", "float32"}:
                    asr_cfg.compute_type = "int8"
                sys.stderr.write("Retrying ASR init on CPU...\n")
                spare_asr = _decode_preflight(asr_cfg)
            else:
                raise SystemExit(1)
    elif device_is_cuda:
        # Non-interactive GPU service (the GUI launcher): warm the model AFTER the port
        # binds, on a background thread, so the client gets a live /health immediately
        # instead of a refused connection during the (possibly doubled, on the CUDA->CPU
        # fallback) model load. The warmup auto-falls-back to CPU exactly as the old
        # non-interactive path did, and resolves asr_cfg.device before any stream starts.
        warm_in_background = True
    # CPU device: no preflight; the first stream loads its worker on demand (unchanged).
    session_id = get_env("WHAT_SESSION_ID") or make_session_label(output_cfg.jsonl_dir)
    session_key = session_id
    print(f"what session_id={session_id} session_key={session_key}")

    app = create_app(audio_cfg, vad_cfg, asr_cfg, output_cfg, service_cfg, session_id, session_key,
                     spare_asr=spare_asr, warm_in_background=warm_in_background)
    uvicorn.run(
        app,
        host=service_cfg.host,
        port=service_cfg.port,
        log_level="info",
        timeout_graceful_shutdown=2,
    )
