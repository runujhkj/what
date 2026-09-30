import subprocess
from array import array
from math import sqrt


def _build_source_input_args(source_kind: str, input_cfg) -> list[str]:
    if source_kind == "mic":
        if input_cfg.mic_backend == "pulse":
            return ["-f", "pulse", "-i", input_cfg.mic_device]
        if input_cfg.mic_backend == "alsa":
            return ["-f", "alsa", "-i", input_cfg.mic_device]
        if input_cfg.mic_backend == "avfoundation":
            from .live_audio import _avf_mic_device
            return ["-f", "avfoundation", "-i", _avf_mic_device(input_cfg.mic_device)]
        if input_cfg.mic_backend == "dshow":
            from .desktop_audio import build_dshow_mic_args
            return build_dshow_mic_args(input_cfg.mic_device)
        raise ValueError(f"Unsupported mic backend: {input_cfg.mic_backend}")
    if source_kind == "desktop":
        from .desktop_audio import build_desktop_input_args

        return build_desktop_input_args(input_cfg.desktop_backend, input_cfg.desktop_device)
    raise ValueError(f"Unsupported source probe kind: {source_kind}")


def _decode_pcm_samples(pcm_bytes: bytes) -> array:
    samples = array("h")
    if not pcm_bytes:
        return samples
    samples.frombytes(pcm_bytes[: len(pcm_bytes) - (len(pcm_bytes) % 2)])
    return samples


def _measure_pcm_signal(pcm_bytes: bytes) -> dict[str, int | str]:
    samples = _decode_pcm_samples(pcm_bytes)
    if not samples:
        return {"state": "error", "level": -1}
    avg_abs = sum(abs(x) for x in samples) / len(samples)
    peak = max(abs(x) for x in samples)
    rms = sqrt(sum(float(x) * float(x) for x in samples) / len(samples))
    # Treat very low-energy captures as silence, but avoid over-classifying
    # valid low-volume desktop program audio as silent.
    state = "signal"
    if peak < 20 and avg_abs < 6:
        state = "silent"
    level = int(round(min(100.0, max(0.0, (rms / 32767.0) * 100.0))))
    return {
        "state": state,
        "level": level,
        "peak": int(peak),
        "avg_abs": int(round(avg_abs)),
        "rms": int(round(rms)),
    }


def measure_live_source(source_kind: str, input_cfg, audio_cfg, duration_sec: float = 0.35) -> dict[str, int | str]:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        *(_build_source_input_args(source_kind, input_cfg)),
        "-t",
        f"{duration_sec:.2f}",
        "-ac",
        str(audio_cfg.channels),
        "-ar",
        str(audio_cfg.sample_rate),
        "-f",
        "s16le",
        "-",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=max(2.0, duration_sec + 1.0))
    except Exception as exc:
        return {"state": "error", "level": -1, "error": str(exc)}
    if result.returncode != 0 and not result.stdout:
        return {
            "state": "error",
            "level": -1,
            "code": int(result.returncode),
            "stderr": str(result.stderr or "").strip()[:240],
        }
    measured = _measure_pcm_signal(result.stdout or b"")
    measured["code"] = int(result.returncode)
    measured["bytes"] = int(len(result.stdout or b""))
    if result.returncode != 0:
        measured["stderr"] = str(result.stderr or "").strip()[:240]
    return measured


def probe_live_source(source_kind: str, input_cfg, audio_cfg, duration_sec: float = 0.35) -> str:
    measured = measure_live_source(source_kind, input_cfg, audio_cfg, duration_sec=duration_sec)
    return str(measured.get("state", "error"))


def probe_live_sources(input_cfg, audio_cfg) -> dict[str, str]:
    out: dict[str, str] = {}
    if getattr(input_cfg, "mic_enabled", False):
        out["mic"] = probe_live_source("mic", input_cfg, audio_cfg)
    if getattr(input_cfg, "desktop_enabled", False):
        out["desktop"] = probe_live_source("desktop", input_cfg, audio_cfg)
    return out


def measure_live_sources(input_cfg, audio_cfg, duration_sec: float = 0.2) -> dict[str, dict[str, int | str]]:
    out: dict[str, dict[str, int | str]] = {}
    if getattr(input_cfg, "mic_enabled", False):
        out["mic"] = measure_live_source("mic", input_cfg, audio_cfg, duration_sec=duration_sec)
    if getattr(input_cfg, "desktop_enabled", False):
        out["desktop"] = measure_live_source("desktop", input_cfg, audio_cfg, duration_sec=duration_sec)
    return out
