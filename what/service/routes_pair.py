from fastapi import FastAPI, HTTPException, Request

from .runtime import ServiceRuntime
from .tokens import mint_token


def register_pair(app: FastAPI, runtime: ServiceRuntime) -> None:
    @app.post(runtime.service_cfg.pair_path)
    async def pair(request: Request) -> dict[str, str]:
        key = request.headers.get("X-What-Session", "")
        if not key:
            key = request.query_params.get("session_key", "")
        if key != runtime.session_key:
            if runtime.service_cfg.local_pair and _is_local_request(request) and not key:
                token = mint_token(runtime)
                return {"token": token, "session_id": runtime.session_id}
            raise HTTPException(status_code=403, detail="unauthorized session key")
        token = mint_token(runtime)
        return {"token": token, "session_id": runtime.session_id}


def _is_local_request(request: Request) -> bool:
    client = request.client
    if client is None:
        return False
    host = client.host
    return host in {"127.0.0.1", "::1"}
