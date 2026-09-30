from fastapi import FastAPI

from ..gpu import detect_gpu


def register_gpu(app: FastAPI) -> None:
    @app.get("/gpu")
    async def gpu() -> dict[str, object]:
        info = detect_gpu()
        return {
            "available": info.available,
            "device": info.device,
            "device_count": info.device_count,
            "backend": info.backend,
            "reason": info.reason,
            "accelerators": list(info.accelerators),
            "engines": list(info.engines),
            "recommended_engine": info.recommended_engine,
        }
