from fastapi import FastAPI

from .runtime import ServiceRuntime


def register_health(app: FastAPI, runtime: ServiceRuntime) -> None:
    @app.get("/health")
    async def health() -> dict[str, str]:
        # "status" stays "ok" whenever the server is up so existing health waits (which
        # only check for a 200) are satisfied as soon as the port binds. "asr" reports the
        # model warmup separately: "loading" while it warms, "ready" once a decode has
        # succeeded, "error" if it could not. Clients can show "loading model" instead of
        # treating a slow first start as a failure.
        payload = {
            "status": "ok",
            "session_id": runtime.session_id,
            "asr": runtime.asr_status,
        }
        if runtime.asr_status == "error" and runtime.asr_error:
            payload["asr_error"] = runtime.asr_error
        return payload
