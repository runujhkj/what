"""ASR warmup: load the model and force one real decode.

Constructing WhisperASR only loads the model, which CTranslate2 can do without
cuBLAS/cuDNN present -- it links them lazily and raises "Library libcublas.so.12 is
not found or cannot be loaded" from the first encode(). A load-only check therefore
passes on a box with missing CUDA libs, so the transcription thread later dies on the
first live chunk while the service stays "healthy" and records audio but emits no
captions. Decoding a second of silence here makes that failure surface up front, where
the CPU fallback can catch it.
"""

from __future__ import annotations

import os
import sys
import threading

from ..asr import WhisperASR, effective_compute_type, supported_compute_types

# 1 second of 16 kHz mono int16 silence.
_SILENCE = b"\x00" * 32000


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.environ.get(name, "")).strip() or default)
    except (TypeError, ValueError):
        return default


def decode_preflight(asr_cfg):
    """Construct a WhisperASR and force one real decode, returning the warmed engine.

    Raising here means the engine cannot actually decode with this configuration; the
    caller decides whether to fall back to CPU.
    """
    asr = WhisperASR(asr_cfg)
    try:
        asr.transcribe(_SILENCE)
    except Exception:
        asr.close()
        raise
    return asr


# Largest -> smallest. Used to pick the next smaller model when the GPU is too full for
# the configured one, before giving up on the GPU entirely.
_MODEL_CHAIN = ["large-v3", "large-v2", "large", "medium", "small", "base", "tiny"]

# Rough steady-state VRAM per worker in float16, MiB. Used only to honor a user VRAM budget;
# ctranslate2 has no hard cap, so this maps a budget to the biggest model/compute that fits.
# Approximate and deliberately a little generous; the observed medium footprint was ~2.2 GB.
_VRAM_BASE_MB = {
    "large-v3": 4500, "large-v2": 4500, "large": 4500,
    "medium": 2200, "small": 1100, "base": 700, "tiny": 500,
}
_VRAM_CONTEXT_MB = 400  # CUDA context + cuDNN workspace floor


def _smaller_model(model: str):
    try:
        idx = _MODEL_CHAIN.index(str(model))
    except ValueError:
        return None
    return _MODEL_CHAIN[idx + 1] if idx + 1 < len(_MODEL_CHAIN) else None


def _models_from(model: str):
    try:
        idx = _MODEL_CHAIN.index(str(model))
    except ValueError:
        return [str(model)]
    return _MODEL_CHAIN[idx:]


def estimate_vram_mb(model: str, compute: str):
    """Estimated per-worker VRAM (MiB) for a model+compute, or None if unknown."""
    base = _VRAM_BASE_MB.get(str(model))
    if base is None:
        return None
    compute = str(compute)
    if compute.startswith("int8"):
        factor = 0.65  # int8 weights ~ 0.65x
    elif compute == "float32":
        factor = 1.8  # GPUs without fast float16 (e.g. GTX 10-series) run float32
    else:
        factor = 1.0
    return max(_VRAM_CONTEXT_MB, int(base * factor))


def fallback_steps(asr_cfg, budget_mb: int = 0, max_workers: int = 2, supported=None):
    """Ordered (label, device, compute_type, model_size) attempts.

    For a CUDA start this descends a ladder that keeps work on the GPU before dropping to
    the CPU: as configured -> int8 (about half the VRAM) -> a smaller model -> CPU. This
    survives a GPU that is only partly free, where the old behaviour collapsed straight to a
    CPU decode that could not keep up. A non-CUDA start yields a single configured attempt.

    When `budget_mb` > 0 the GPU rungs are instead every model+compute (from the configured
    size down) whose estimated footprint fits the per-worker budget (`budget_mb / max_workers`,
    since mic and desktop each load one worker), largest-fitting first, then CPU. If nothing
    fits the budget, only CPU remains -- honoring "no more than X GB on the GPU".

    `supported` is the GPU's CTranslate2 compute types (None = unknown): each rung uses the
    type that will actually run, so a float16-less GPU is budgeted at its float32 size and
    rungs that collapse to the same attempt are tried once.
    """
    device = str(getattr(asr_cfg, "device", "") or "").lower()
    model = str(getattr(asr_cfg, "model_size", "") or "")
    compute = str(getattr(asr_cfg, "compute_type", "") or "")

    def eff(c):
        return effective_compute_type(c, supported)

    if not device.startswith("cuda"):
        return [("configured", asr_cfg.device, asr_cfg.compute_type, asr_cfg.model_size)]

    if budget_mb and int(budget_mb) > 0:
        per_worker = int(budget_mb) / max(1, int(max_workers))
        # A custom model_path can't be resized; only vary its compute.
        models = [model] if getattr(asr_cfg, "model_path", None) else _models_from(model)
        cands = []
        seen = set()
        for m in models:
            for c in [eff(compute or "float16"), eff("int8_float16")]:
                if (m, c) in seen:
                    continue
                seen.add((m, c))
                est = estimate_vram_mb(m, c)
                if est is not None and est <= per_worker:
                    cands.append((f"cuda:{m}/{c}", "cuda", c, m, est))
        cands.sort(key=lambda x: x[4], reverse=True)  # biggest that fits first
        steps = [(lbl, dev, comp, mdl) for (lbl, dev, comp, mdl, _est) in cands]
        steps.append(("cpu", "cpu", "int8", model))
        return steps

    first = eff(compute or "float16")
    int8 = eff("int8_float16")
    steps = [("cuda", "cuda", first, model)]
    if compute not in {"int8", "int8_float16"} and int8 != first:
        steps.append(("cuda-int8", "cuda", int8, model))
    # Only swap the model when the size is what selects it (not a custom model_path).
    if not getattr(asr_cfg, "model_path", None):
        smaller = _smaller_model(model)
        if smaller:
            steps.append(("cuda-small", "cuda", int8, smaller))
    steps.append(("cpu", "cpu", "int8", model))
    return steps


def resolve_engine_with_fallback(asr_cfg, log, preflight=None, budget_mb=0, max_workers=2):
    """Walk `fallback_steps`, applying each to asr_cfg and preflighting, until one works.

    Mutates asr_cfg in place to the winning device/compute/model so the stream workers
    reuse exactly what was verified. `budget_mb` caps GPU VRAM (see fallback_steps). Raises
    the last error if nothing works.
    """
    # Resolve at call time (not as a default arg) so tests can monkeypatch decode_preflight.
    if preflight is None:
        preflight = decode_preflight
    supported = None
    if str(getattr(asr_cfg, "device", "") or "").lower().startswith("cuda"):
        supported = supported_compute_types("cuda", getattr(asr_cfg, "device_index", 0))
    steps = fallback_steps(asr_cfg, budget_mb=budget_mb, max_workers=max_workers, supported=supported)
    if not steps:
        raise RuntimeError("no ASR configuration is available for these settings")
    last_exc = None
    for label, device, compute, model in steps:
        asr_cfg.device = device
        asr_cfg.compute_type = compute
        asr_cfg.model_size = model
        try:
            asr = preflight(asr_cfg)
            log(f"ASR ready via {label}: device={device} compute={compute} model={model}\n")
            return asr
        except Exception as exc:  # noqa: BLE001 - try the next rung of the ladder
            last_exc = exc
            log(f"ASR {label} failed ({exc}); trying next fallback\n")
    raise last_exc or RuntimeError("no ASR configuration could start")


# Headroom left free for the display, other apps and CUDA allocator slack.
_AUTO_BUDGET_MARGIN_MB = 512


def auto_budget_mb(asr_cfg, query=None) -> int:
    """VRAM currently free on the configured GPU minus a margin, or 0 if unknown.

    Used when the user set no budget. A model that doesn't fit usually still "loads":
    Windows' driver spills into system RAM and Linux may OOM later, so the ladder, which
    only steps down on a load failure, would keep an oversized model that can't keep up.
    """
    if not str(getattr(asr_cfg, "device", "") or "").lower().startswith("cuda"):
        return 0
    if query is None:
        from ..gpu import nvidia_memory as query
    try:
        gpus = query()
        gpu = gpus[int(getattr(asr_cfg, "device_index", 0) or 0)]
        free = int(gpu["total_mb"]) - int(gpu["used_mb"])
    except (IndexError, KeyError, TypeError, ValueError):
        return 0
    return max(0, free - _AUTO_BUDGET_MARGIN_MB)


def warm_up_in_background(runtime) -> None:
    """Warm the ASR after the HTTP port is already bound, updating readiness state.

    Runs on its own thread so uvicorn can serve /health immediately instead of the client
    seeing the service never come up while the model loads. This is the non-interactive
    path used by the GUI-launched service: it walks the GPU->CPU fallback ladder rather
    than waiting on an invisible prompt. `runtime.asr_cfg` is resolved to its final
    device/compute/model before `asr_ready_event` is set, so the first stream worker (which
    waits on that event) never races ahead with a stale config.
    """

    budget_mb = _env_int("WHAT_GPU_MEM_BUDGET_MB", 0)
    max_workers = _env_int("WHAT_GPU_MAX_WORKERS", 2)
    source = "user limit"
    if budget_mb <= 0 and os.environ.get("WHAT_GPU_AUTO_BUDGET", "1").lower() not in {"0", "false", "no"}:
        budget_mb = auto_budget_mb(runtime.asr_cfg)
        source = "free VRAM"

    def _run() -> None:
        try:
            if budget_mb > 0:
                sys.stderr.write(
                    f"ASR GPU budget: {budget_mb} MiB total ({source}, {max_workers} workers);"
                    f" choosing the largest model that fits.\n"
                )
            runtime.spare_asr = resolve_engine_with_fallback(
                runtime.asr_cfg, log=lambda m: sys.stderr.write(m),
                budget_mb=budget_mb, max_workers=max_workers,
            )
            runtime.asr_status = "ready"
        except Exception as exc:  # noqa: BLE001 - report, do not crash the service
            runtime.asr_status = "error"
            runtime.asr_error = str(exc)
            sys.stderr.write(f"ASR warmup failed: {exc}\n")
        finally:
            runtime.asr_ready_event.set()

    threading.Thread(target=_run, name="asr-warmup", daemon=True).start()
