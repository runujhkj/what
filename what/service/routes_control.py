from fastapi import FastAPI, Request

from .runtime import ServiceRuntime

# Runtime-tunable ASR fields. WhisperASR reads its config per-decode, so mutating
# runtime.asr_cfg under asr_lock takes effect on the NEXT chunk -- no restart. Only
# decode-time knobs are listed; model_size/compute_type/device need a rebuild and
# are intentionally excluded.
_FLOAT_FIELDS = (
    "min_avg_logprob",
    "no_speech_threshold",
    "logprob_threshold",
    "compression_ratio_threshold",
)
_INT_FIELDS = ("beam_size",)
_BOOL_FIELDS = ("condition_on_previous_text",)


def _snapshot(cfg) -> dict:
    return {k: getattr(cfg, k) for k in (_FLOAT_FIELDS + _INT_FIELDS + _BOOL_FIELDS)}


def register_control(app: FastAPI, runtime: ServiceRuntime) -> None:
    @app.get("/control/asr")
    async def get_asr() -> dict:
        with runtime.asr_lock:
            return {"asr": _snapshot(runtime.asr_cfg)}

    @app.post("/control/asr")
    async def set_asr(request: Request) -> dict:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        updated: dict = {}
        with runtime.asr_lock:
            cfg = runtime.asr_cfg
            for key, value in body.items():
                try:
                    if key in _FLOAT_FIELDS:
                        setattr(cfg, key, float(value))
                    elif key in _INT_FIELDS:
                        setattr(cfg, key, int(value))
                    elif key in _BOOL_FIELDS:
                        setattr(cfg, key, bool(value))
                    else:
                        continue
                except (TypeError, ValueError):
                    continue
                updated[key] = getattr(cfg, key)
            snap = _snapshot(cfg)
        return {"ok": True, "updated": updated, "asr": snap}
