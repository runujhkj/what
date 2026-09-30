from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .lifecycle import build_service_lifespan
from .routes_control import register_control
from .routes_events import register_events
from .routes_gpu import register_gpu
from .routes_health import register_health
from .routes_http import register_http
from .routes_pair import register_pair
from .routes_stats import register_stats
from .routes_ws import register_ws
from .runtime import ServiceRuntime


def create_app(
    audio_cfg,
    vad_cfg,
    asr_cfg,
    output_cfg,
    service_cfg,
    session_id: str,
    session_key: str,
    spare_asr=None,
    warm_in_background: bool = False,
) -> FastAPI:
    runtime = ServiceRuntime(
        audio_cfg=audio_cfg,
        vad_cfg=vad_cfg,
        asr_cfg=asr_cfg,
        output_cfg=output_cfg,
        service_cfg=service_cfg,
        session_id=session_id,
        session_key=session_key,
        spare_asr=spare_asr,
        warm_in_background=warm_in_background,
    )
    app = FastAPI(title="what", lifespan=build_service_lifespan(runtime))
    # Allow cross-origin readers of /events (OBS browser-source overlay loaded from a
    # file:// or other origin) to subscribe -- without this, EventSource is CORS-
    # blocked. LAN service, so a permissive policy is fine.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_health(app, runtime)
    register_pair(app, runtime)
    register_gpu(app)
    register_events(app, runtime)
    register_stats(app, runtime)
    register_ws(app, runtime)
    register_http(app, runtime)
    register_control(app, runtime)
    return app
