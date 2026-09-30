from dataclasses import dataclass
import os
from typing import Any, Protocol

import inspect


@dataclass
class AsrConfig:
    model_size: str
    compute_type: str
    beam_size: int
    language: str
    device: str
    device_index: int
    min_avg_logprob: float
    no_speech_threshold: float
    logprob_threshold: float
    compression_ratio_threshold: float
    condition_on_previous_text: bool
    engine: str = "auto"
    model_path: str | None = None
    worker_path: str | None = None
    worker_timeout_seconds: float = 15.0


class AsrEngine(Protocol):
    """Engine-neutral synchronous ASR contract used by the streaming pipeline."""

    def transcribe(self, pcm_bytes: bytes) -> dict[str, Any]: ...

    def close(self) -> None: ...


# Model downloads go through huggingface_hub. Its symlink warning (Windows without Developer
# Mode; the cache still works, using copies) and server notices such as the anonymous
# rate-limit hint are noise in the app's log. Must be set before huggingface_hub imports.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_VERBOSITY", "error")

# Nearest substitutes, best first, for a compute type the device can't run efficiently.
# Without fast float16 (e.g. GTX 10-series), int8 beats float32: half the VRAM and faster
# (DP4A), with negligible accuracy loss for Whisper. float32 medium x2 workers overfilled an
# 8 GB GTX 1080 and decoded at ~3x real time.
_COMPUTE_FALLBACKS = {
    "float16": ("bfloat16", "int8_float32", "float32"),
    "bfloat16": ("float16", "int8_float32", "float32"),
    "int8_float16": ("int8_bfloat16", "int8_float32", "int8"),
    "int8_bfloat16": ("int8_float16", "int8_float32", "int8"),
}


def supported_compute_types(device: str, device_index: int = 0):
    """CTranslate2's supported compute types for a device, or None if it can't be queried."""
    try:
        import ctranslate2

        return set(ctranslate2.get_supported_compute_types(device, int(device_index or 0)))
    except Exception:
        return None


def effective_compute_type(compute_type: str, supported) -> str:
    """`compute_type`, or its nearest supported substitute when `supported` excludes it."""
    if not supported or not compute_type or compute_type in supported:
        return compute_type
    for alt in _COMPUTE_FALLBACKS.get(compute_type, ()):
        if alt in supported:
            return alt
    return compute_type


class FasterWhisperASR:
    def __init__(self, cfg: AsrConfig) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError("faster-whisper is required for the faster_whisper engine") from exc
        self.cfg = cfg
        if str(cfg.device).startswith("cuda"):
            # e.g. GTX 10-series (Pascal) GPUs reject float16; use the nearest supported type
            # rather than failing the GPU outright. Written back so logs report what ran.
            cfg.compute_type = effective_compute_type(
                cfg.compute_type, supported_compute_types("cuda", cfg.device_index)
            )
        kwargs = {
            "device": cfg.device,
            "compute_type": cfg.compute_type,
        }
        if cfg.device != "cpu":
            kwargs["device_index"] = cfg.device_index
        init_sig = inspect.signature(WhisperModel.__init__)
        kwargs = {k: v for k, v in kwargs.items() if k in init_sig.parameters}
        self.model = WhisperModel(cfg.model_size, **kwargs)
        self._supported_kwargs = self._get_supported_kwargs()

    def _get_supported_kwargs(self) -> set[str]:
        try:
            sig = inspect.signature(self.model.transcribe)
        except (TypeError, ValueError):
            return set()
        return set(sig.parameters.keys())

    def transcribe(self, pcm_bytes: bytes) -> dict[str, Any]:
        import numpy as np

        audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        kwargs = {
            "language": self.cfg.language,
            "beam_size": self.cfg.beam_size,
            "no_speech_threshold": self.cfg.no_speech_threshold,
            "logprob_threshold": self.cfg.logprob_threshold,
            "compression_ratio_threshold": self.cfg.compression_ratio_threshold,
            "condition_on_previous_text": self.cfg.condition_on_previous_text,
            "vad_filter": False,
            # Per-word timings, which the pipeline forwards as `words` for word-level
            # click-to-replay in the review UI. Without this every segment arrived with
            # words=[] and a click could only seek to the segment's start. Measured cost
            # on CUDA/float16 is ~6% of decode time (13ms on medium), so it stays on;
            # _supported_kwargs drops it on faster_whisper builds that lack it.
            "word_timestamps": True,
        }
        if self._supported_kwargs:
            kwargs = {k: v for k, v in kwargs.items() if k in self._supported_kwargs}
        segments, info = self.model.transcribe(audio, **kwargs)

        seg_list = []
        best_avg_logprob = None
        text_parts = []
        for seg in segments:
            text_parts.append(seg.text)
            if best_avg_logprob is None or seg.avg_logprob > best_avg_logprob:
                best_avg_logprob = seg.avg_logprob
            seg_list.append(
                {
                    "start": float(seg.start),
                    "end": float(seg.end),
                    "text": seg.text,
                    "avg_logprob": float(seg.avg_logprob),
                    # Segment-relative; pipeline.py shifts them to absolute session time.
                    "words": [
                        {
                            "word": getattr(w, "word", ""),
                            "start": float(getattr(w, "start", 0.0)),
                            "end": float(getattr(w, "end", 0.0)),
                        }
                        for w in (getattr(seg, "words", None) or [])
                    ],
                }
            )

        text = "".join(text_parts).strip()
        return {
            "text": text,
            "segments": seg_list,
            "language": info.language,
            "language_probability": float(info.language_probability),
            "best_avg_logprob": float(best_avg_logprob) if best_avg_logprob is not None else None,
        }

    def close(self) -> None:
        """CTranslate2 resources are released when this engine is collected."""


def resolve_engine_name(cfg: AsrConfig) -> str:
    """Select a platform default without leaking device-specific choices upstream."""
    if cfg.engine and cfg.engine != "auto":
        return cfg.engine
    import platform

    if platform.system() == "Darwin" and platform.machine().lower() in {"arm64", "aarch64"}:
        return "whisperkit"
    return "faster_whisper"


def create_asr_engine(cfg: AsrConfig) -> AsrEngine:
    engine = resolve_engine_name(cfg)
    if engine == "faster_whisper":
        return FasterWhisperASR(cfg)
    if engine == "whisperkit":
        from .whisperkit_worker import WhisperKitWorkerASR

        return WhisperKitWorkerASR(cfg)
    if engine == "whisper_cpp":
        from .whisper_cpp_worker import WhisperCppWorkerASR

        return WhisperCppWorkerASR(cfg)
    raise ValueError(f"unsupported ASR engine: {engine}")


class WhisperASR:
    """Compatibility façade; new callers should use ``create_asr_engine``."""

    def __init__(self, cfg: AsrConfig) -> None:
        self.engine = create_asr_engine(cfg)

    def transcribe(self, pcm_bytes: bytes) -> dict[str, Any]:
        return self.engine.transcribe(pcm_bytes)

    def close(self) -> None:
        self.engine.close()
