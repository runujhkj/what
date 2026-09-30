import asyncio
import logging
import os
import threading

from fastapi import FastAPI, Request

logger = logging.getLogger(__name__)


def _preload_backend() -> None:
    """Download and warm the model in a daemon thread at startup."""
    try:
        from ..llm_cleanup import get_backend
        backend = get_backend()
        if hasattr(backend, "_ensure_loaded"):
            backend._ensure_loaded()
            logger.info("llm_cleanup: model preloaded")
    except Exception as exc:
        logger.warning("llm_cleanup: preload failed: %s", exc)


def _preload_requested() -> bool:
    return os.environ.get("WHAT_LLM_CLEANUP_PRELOAD", "").strip().lower() in {"1", "true", "yes", "on"}


def register_cleanup_routes(app: FastAPI) -> None:
    # The cleanup model is only used by /control/cleanup (the older UI), so it loads on
    # first request. Preloading at every controller start contacted Hugging Face and
    # loaded an MLX model even when nothing used it; opt in with WHAT_LLM_CLEANUP_PRELOAD=1.
    if _preload_requested():
        threading.Thread(target=_preload_backend, daemon=True, name="llm-preload").start()

    @app.post("/control/cleanup")
    async def cleanup(request: Request) -> dict:
        body = await request.json()
        text = str(body.get("text", "") or "").strip()
        if not text:
            return {"ok": False, "error": "empty_text"}

        from ..llm_cleanup import get_backend
        backend = get_backend()

        if not backend.available:
            return {"ok": False, "error": "backend_unavailable"}

        try:
            loop = asyncio.get_running_loop()
            cleaned = await loop.run_in_executor(None, backend.clean, text)
            return {"ok": True, "text": cleaned}
        except Exception as exc:
            logger.exception("llm_cleanup error")
            return {"ok": False, "error": str(exc)}
