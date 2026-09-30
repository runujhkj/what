from fastapi import FastAPI

from .runtime import ServiceRuntime


def register_stats(app: FastAPI, runtime: ServiceRuntime) -> None:
    @app.get("/stats")
    async def stats() -> dict[str, float | int]:
        snap = runtime.stats.snapshot()
        return {
            "samples": snap.samples,
            "avg_rtf": snap.avg_rtf,
            "avg_processing_ms": snap.avg_processing_ms,
            "avg_audio_ms": snap.avg_audio_ms,
            "last_update": snap.last_update,
        }
