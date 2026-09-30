from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request

from ..gpu import detect_gpu
from . import desktop_audio_manager
from .controller_payloads import (
    merge_settings as _merge_settings_impl,
    merge_stream_settings as _merge_stream_settings_impl,
    read_json as _read_json_impl,
)
from .controller_route_utils import (
    append_stream_log as _append_stream_log_impl,
    close_process_log as _close_process_log_impl,
    ensure_process_session as _ensure_process_session_impl,
    read_service_health as _read_service_health_impl,
    resolve_log_root as _resolve_log_root_impl,
    start_stream_log_pump as _start_stream_log_pump_impl,
    wait_for_service_health as _wait_for_service_health_impl,
)
from .controller_settings_store import (
    clamp_float as _clamp_float_impl,
    clamp_int as _clamp_int_impl,
    desktop_audio_receipt_path as _desktop_audio_receipt_path_impl,
    load_persisted_settings as _load_persisted_settings_impl,
    persist_settings as _persist_settings_impl,
    settings_store_path as _settings_store_path_impl,
)
from .process import (
    REPO_ROOT,
    process_running,
    start_client,
    start_service,
    stop_client,
    stop_service,
)
from .routes_cleanup import register_cleanup_routes
from .routes_control import register_control_routes
from .routes_desktop_audio import register_desktop_audio_routes
from .routes_stream import register_stream_routes
from .stream_event_lane import (
    start_stream_event_lane as _start_stream_event_lane_impl,
    stop_stream_event_lane as _stop_stream_event_lane_impl,
)
from .state import ControlSettings, ControllerState, StreamSettings
from .types import ControllerConfig


def create_controller_app(cfg: ControllerConfig, state: ControllerState) -> FastAPI:
    _load_persisted_settings(cfg, state)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
            _stop_stream_event_lane_impl(state=state)
            stop_client(state.client_process)
            stop_service(state.process)
            _close_process_log(state, clear_session=True)

    app = FastAPI(title="what-controller", lifespan=lifespan)

    register_cleanup_routes(app)

    register_control_routes(
        app,
        cfg,
        state,
        repo_root=REPO_ROOT,
        desktop_audio_manager_mod=desktop_audio_manager,
        process_running_fn=process_running,
        start_service_fn=start_service,
        stop_service_fn=stop_service,
        start_client_fn=start_client,
        stop_client_fn=stop_client,
        read_json=_read_json,
        merge_settings=_merge_settings,
        merge_stream_settings=_merge_stream_settings,
        wait_for_service_health=_wait_for_service_health,
        append_stream_log=_append_stream_log,
        start_stream_log_pump=_start_stream_log_pump,
        persist_settings=_persist_settings,
        close_process_log=_close_process_log,
        ensure_process_session=_ensure_process_session,
        clamp_int=_clamp_int,
        clamp_float=_clamp_float,
        desktop_audio_receipt_path=_desktop_audio_receipt_path,
        detect_gpu_fn=detect_gpu,
    )

    register_stream_routes(
        app,
        cfg,
        state,
        repo_root=REPO_ROOT,
        desktop_audio_manager_mod=desktop_audio_manager,
        desktop_audio_receipt_path=_desktop_audio_receipt_path,
        process_running_fn=process_running,
        start_service_fn=start_service,
        start_client_fn=start_client,
        stop_client_fn=stop_client,
        read_json=_read_json,
        merge_stream_settings=_merge_stream_settings,
        wait_for_service_health=_wait_for_service_health,
        ensure_process_session=_ensure_process_session,
        append_stream_log=_append_stream_log,
        start_stream_log_pump=_start_stream_log_pump,
        persist_settings=_persist_settings,
        start_stream_event_lane=_start_stream_event_lane,
        stop_stream_event_lane=_stop_stream_event_lane,
    )

    register_desktop_audio_routes(
        app,
        cfg,
        state,
        repo_root=REPO_ROOT,
        desktop_audio_manager_mod=desktop_audio_manager,
        read_json=_read_json,
        ensure_process_session=_ensure_process_session,
        append_stream_log=_append_stream_log,
        desktop_audio_receipt_path=_desktop_audio_receipt_path,
    )

    return app


async def _read_json(request: Request) -> dict:
    return await _read_json_impl(request)


def _merge_settings(
    current: ControlSettings, payload: dict, require_profile: bool
) -> ControlSettings:
    return _merge_settings_impl(
        current,
        payload,
        require_profile=require_profile,
        clamp_int=_clamp_int,
        clamp_float=_clamp_float,
    )


def _merge_stream_settings(current: StreamSettings, payload: dict) -> StreamSettings:
    return _merge_stream_settings_impl(current, payload)


def _append_stream_log(
    state: ControllerState,
    line: str,
    *,
    count_for_heartbeat: bool = True,
) -> None:
    _append_stream_log_impl(state, line, count_for_heartbeat=count_for_heartbeat)


def _start_stream_log_pump(state: ControllerState, proc) -> None:
    _start_stream_log_pump_impl(state, proc, _append_stream_log)


def _start_stream_event_lane(cfg: ControllerConfig, state: ControllerState) -> None:
    _start_stream_event_lane_impl(
        cfg=cfg,
        state=state,
        append_log=_append_stream_log,
        process_running=process_running,
    )


def _stop_stream_event_lane(state: ControllerState) -> None:
    _stop_stream_event_lane_impl(state=state)


def _wait_for_service_health(host: str, port: int, timeout_s: float) -> None:
    _wait_for_service_health_impl(host, port, timeout_s)


def _read_service_health(host: str, port: int) -> dict[str, object]:
    return _read_service_health_impl(host, port)


def _resolve_log_root(cfg: ControllerConfig) -> Path:
    return _resolve_log_root_impl(cfg, REPO_ROOT)


def _close_process_log(state: ControllerState, clear_session: bool) -> None:
    _close_process_log_impl(state, clear_session)


def _ensure_process_session(cfg: ControllerConfig, state: ControllerState) -> str:
    return _ensure_process_session_impl(
        cfg=cfg,
        state=state,
        repo_root=REPO_ROOT,
        process_running=process_running,
        append_log=_append_stream_log,
        read_service_health_fn=_read_service_health,
        resolve_log_root_fn=lambda c, _root: _resolve_log_root(c),
    )


def _settings_store_path(cfg: ControllerConfig) -> str:
    return _settings_store_path_impl(cfg)


def _desktop_audio_receipt_path(cfg: ControllerConfig) -> str:
    return _desktop_audio_receipt_path_impl(cfg)


def _persist_settings(cfg: ControllerConfig, state: ControllerState) -> None:
    _persist_settings_impl(cfg, state)


def _clamp_int(value, min_value: int, max_value: int, fallback: int) -> int:
    return _clamp_int_impl(value, min_value, max_value, fallback)


def _clamp_float(value, min_value: float, max_value: float, fallback: float) -> float:
    return _clamp_float_impl(value, min_value, max_value, fallback)


def _load_persisted_settings(cfg: ControllerConfig, state: ControllerState) -> None:
    _load_persisted_settings_impl(cfg, state)
