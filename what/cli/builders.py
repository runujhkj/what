import platform

from ..audio import AudioConfig, InputConfig
from ..desktop_audio import default_desktop_backend, normalize_desktop_backend
from ..env import get_env


def build_audio_cfg(args, cfg: dict) -> AudioConfig:
    boundary_points = cfg["audio"].get("boundary_candidate_points", 3)
    if args.boundary_candidate_points is not None:
        boundary_points = args.boundary_candidate_points
    return AudioConfig(
        sample_rate=cfg["audio"]["sample_rate"],
        channels=cfg["audio"]["channels"],
        frame_ms=cfg["audio"]["frame_ms"] if args.frame_ms is None else args.frame_ms,
        chunk_ms=cfg["audio"]["chunk_ms"] if args.chunk_ms is None else args.chunk_ms,
        overlap_ms=cfg["audio"]["overlap_ms"] if args.overlap_ms is None else args.overlap_ms,
        boundary_candidate_points=max(1, min(7, int(boundary_points))),
    )


def build_input_cfg(args, cfg: dict) -> InputConfig:
    env_input = get_env("WHAT_INPUT")
    env_backend = get_env("WHAT_MIC_BACKEND")
    env_device = get_env("WHAT_MIC_DEVICE")
    env_mic_enabled = get_env("WHAT_MIC_ENABLED")
    env_desktop_backend = get_env("WHAT_DESKTOP_BACKEND")
    env_desktop_device = get_env("WHAT_DESKTOP_DEVICE")
    env_desktop_enabled = get_env("WHAT_DESKTOP_ENABLED")
    env_file = get_env("WHAT_INPUT_FILE")
    env_realtime = get_env("WHAT_INPUT_REALTIME")

    mic_backend = args.mic_backend or env_backend or cfg["input"]["mic_backend"]
    mic_device = args.mic_device or env_device or cfg["input"]["mic_device"]
    if args.mic_backend is None and env_backend is None:
        system = platform.system().lower()
        if system == "darwin":
            mic_backend = "avfoundation"
            if mic_device == "default":
                mic_device = ":default"
        elif system == "linux":
            mic_backend = "pulse"
        elif system == "windows":
            mic_backend = "dshow"

    desktop_backend = normalize_desktop_backend(
        args.desktop_backend
        or env_desktop_backend
        or cfg["input"].get("desktop_backend")
        or default_desktop_backend()
    )
    desktop_device = (
        args.desktop_device
        or env_desktop_device
        or cfg["input"].get("desktop_device")
        or ""
    )
    selected_mode = args.input or env_input or cfg["input"]["mode"]
    mic_enabled_default = selected_mode == "mic"
    desktop_enabled_default = selected_mode == "desktop"
    mic_enabled = cfg["input"].get("mic_enabled", mic_enabled_default)
    desktop_enabled = cfg["input"].get("desktop_enabled", desktop_enabled_default)
    if env_mic_enabled is not None:
        mic_enabled = env_mic_enabled == "1"
    if env_desktop_enabled is not None:
        desktop_enabled = env_desktop_enabled == "1"
    if args.mic_enabled:
        mic_enabled = True
    if args.no_mic:
        mic_enabled = False
    if args.desktop_enabled:
        desktop_enabled = True
    if args.no_desktop:
        desktop_enabled = False

    return InputConfig(
        mode=selected_mode,
        mic_backend=mic_backend,
        mic_device=mic_device,
        mic_enabled=mic_enabled,
        desktop_backend=desktop_backend,
        desktop_device=desktop_device,
        desktop_enabled=desktop_enabled,
        file_path=args.file or env_file or cfg["input"]["file_path"],
        stdin_raw=args.stdin_raw,
        realtime=args.realtime or (env_realtime == "1"),
        stream_tag=getattr(args, "stream_tag", None),
    )


def build_vad_cfg(args, cfg: dict):
    from ..vad import VadConfig

    enabled = cfg["vad"]["enabled"]
    if args.no_vad:
        enabled = False
    return VadConfig(
        enabled=enabled,
        mode=cfg["vad"]["mode"] if args.vad_mode is None else args.vad_mode,
        speech_ratio=cfg["vad"]["speech_ratio"] if args.vad_speech_ratio is None else args.vad_speech_ratio,
    )


def build_asr_cfg(args, cfg: dict):
    from ..asr import AsrConfig

    return AsrConfig(
        model_size=args.model or get_env("WHAT_SERVICE_MODEL") or cfg["asr"]["model_size"],
        compute_type=args.compute_type or get_env("WHAT_SERVICE_COMPUTE_TYPE") or cfg["asr"]["compute_type"],
        beam_size=cfg["asr"]["beam_size"] if args.beam_size is None else args.beam_size,
        language=args.lang or get_env("WHAT_SERVICE_LANGUAGE") or cfg["asr"]["language"],
        device=args.device or get_env("WHAT_SERVICE_DEVICE") or cfg["asr"]["device"],
        device_index=cfg["asr"].get("device_index", 0) if args.device_index is None else args.device_index,
        min_avg_logprob=cfg["asr"].get("min_avg_logprob", -1.0),
        no_speech_threshold=cfg["asr"].get("no_speech_threshold", 0.6)
        if args.no_speech_threshold is None
        else args.no_speech_threshold,
        logprob_threshold=cfg["asr"].get("logprob_threshold", -1.0)
        if args.logprob_threshold is None
        else args.logprob_threshold,
        compression_ratio_threshold=cfg["asr"].get("compression_ratio_threshold", 2.4)
        if args.compression_ratio_threshold is None
        else args.compression_ratio_threshold,
        condition_on_previous_text=args.condition_on_previous_text
        or cfg["asr"].get("condition_on_previous_text", False),
        engine=args.engine or get_env("WHAT_SERVICE_ENGINE") or cfg["asr"].get("engine", "auto"),
        model_path=args.model_path or get_env("WHAT_SERVICE_MODEL_PATH") or cfg["asr"].get("model_path"),
        worker_path=args.worker_path or get_env("WHAT_SERVICE_WORKER_PATH") or cfg["asr"].get("worker_path"),
        worker_timeout_seconds=float(cfg["asr"].get("worker_timeout_seconds", 15.0)),
    )


WHISPERKIT_DEFAULT_MODEL = "base"
WHISPERKIT_DEFAULT_CHUNK_MS = 2500


def apply_engine_defaults(args, cfg: dict, audio_cfg, asr_cfg) -> None:
    """Replace CUDA-tuned config defaults when the resolved engine is WhisperKit.

    The shared [asr] model/device and caption chunk size are tuned for faster-whisper
    on CUDA, but on Apple Silicon `engine = "auto"` resolves to the WhisperKit (Metal)
    worker. There, `medium` is not a validated Core ML model (an interrupted conversion
    fails to load), `device = "cuda"` misroutes startup failures through the CUDA/CPU
    fallback, and 800 ms chunks cut WhisperKit's full-utterance decoding mid-word.
    Explicit CLI/environment choices are kept; config keys `asr.whisperkit_model_size`
    and `audio.whisperkit_chunk_ms` adjust the WhisperKit defaults.
    """
    from ..asr import resolve_engine_name

    if resolve_engine_name(asr_cfg) != "whisperkit":
        return
    if not (getattr(args, "model", None) or get_env("WHAT_SERVICE_MODEL") or asr_cfg.model_path):
        asr_cfg.model_size = cfg["asr"].get("whisperkit_model_size", WHISPERKIT_DEFAULT_MODEL)
    if not (getattr(args, "device", None) or get_env("WHAT_SERVICE_DEVICE")):
        asr_cfg.device = "auto"
    if getattr(args, "chunk_ms", None) is None:
        audio_cfg.chunk_ms = int(cfg["audio"].get("whisperkit_chunk_ms", WHISPERKIT_DEFAULT_CHUNK_MS))


def build_output_cfg(args, cfg: dict):
    from ..output import OutputConfig

    text_stream = cfg["output"]["text_stream"]
    if args.text_stream:
        text_stream = True
    if args.no_text_stream:
        text_stream = False
    text_block_clear = cfg["output"].get("text_block_clear", False)
    if args.text_block_clear:
        text_block_clear = True
    if args.no_text_block_clear:
        text_block_clear = False
    text_normalize = cfg["output"].get("text_normalize", False)
    if args.text_normalize:
        text_normalize = True
    if args.no_text_normalize:
        text_normalize = False
    return OutputConfig(
        text_stream=text_stream,
        jsonl_log=args.jsonl_log or cfg["output"]["jsonl_log"],
        # WHAT_JSONL_DIR lets a packaged app redirect recordings/transcripts to a writable
        # per-user dir, since the bundled source (the default cwd) is read-only.
        jsonl_dir=args.jsonl_dir or get_env("WHAT_JSONL_DIR") or cfg["output"].get("jsonl_dir", "logs"),
        text_mode=args.text_mode or cfg["output"].get("text_mode", "delta"),
        text_window_segments=cfg["output"].get("text_window_segments", 0)
        if args.text_window_segments is None
        else args.text_window_segments,
        text_window_chars=cfg["output"].get("text_window_chars", 0)
        if args.text_window_chars is None
        else args.text_window_chars,
        text_block_clear=text_block_clear,
        text_normalize=text_normalize,
    )
