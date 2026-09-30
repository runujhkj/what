from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from .native_desktop_backend import native_helper_capabilities
from . import native_desktop_helper_manager
from ..gpu import nvidia_memory


def register_control_routes(
    app: FastAPI,
    cfg,
    state,
    *,
    repo_root,
    desktop_audio_manager_mod,
    process_running_fn,
    start_service_fn,
    stop_service_fn,
    start_client_fn,
    stop_client_fn,
    read_json,
    merge_settings,
    merge_stream_settings,
    wait_for_service_health,
    append_stream_log,
    start_stream_log_pump,
    persist_settings,
    close_process_log,
    ensure_process_session,
    clamp_int,
    clamp_float,
    desktop_audio_receipt_path,
    detect_gpu_fn,
) -> None:
    @app.get("/control/status")
    async def status() -> dict[str, object]:
        running = process_running_fn(state.process)
        stream_running = process_running_fn(state.client_process)
        s = state.settings
        stream = state.stream_settings
        body = {
            "running": running,
            "stream_running": stream_running,
            "service_host": cfg.service_host,
            "service_port": cfg.service_port,
            "profile": s.profile or "",
            "engine": s.engine or "auto",
            "device": s.device or "",
            "device_index": int(s.device_index or 0),
            "compute_type": s.compute_type or "",
            "model_size": s.model_size or "",
            "beam_size": int(s.beam_size or 0),
            "language": s.language or "",
            "no_vad": bool(s.no_vad),
            "publish_delay_seconds": int(s.publish_delay_seconds),
            "boundary_candidate_points": int(s.boundary_candidate_points),
            "overlay_width_px": int(s.overlay_width_px),
            "overlay_height_px": int(s.overlay_height_px),
            "overlay_padding_px": int(s.overlay_padding_px),
            "overlay_font_size_px": float(s.overlay_font_size_px),
            "gpu_mem_budget_mb": int(s.gpu_mem_budget_mb),
            "stream_input_mode": stream.input_mode,
            "stream_file_path": stream.file_path or "",
            "stream_realtime": bool(stream.realtime),
            "stream_mic_enabled": bool(stream.mic_enabled),
            "stream_mic_backend": stream.mic_backend or "",
            "stream_mic_device": stream.mic_device or "",
            "stream_desktop_enabled": bool(stream.desktop_enabled),
            "active_sources": (["mic"] if stream.mic_enabled else []) + (["desktop"] if stream.desktop_enabled else []),
            "stream_desktop_backend": stream.desktop_backend or "",
            "stream_desktop_device": stream.desktop_capture_input or stream.desktop_device or "",
            "stream_desktop_output_target": stream.desktop_output_target or "",
            "stream_desktop_capture_input": stream.desktop_capture_input or "",
            "stream_event_prefix": stream.event_prefix or "",
            "session_id": state.current_session_id or "",
            "desktop_audio_manager": desktop_audio_manager_mod.get_status(
                repo_root, Path(desktop_audio_receipt_path(cfg)), include_routing=False
            ),
            "desktop_native_helper_manager": native_desktop_helper_manager.get_status(
                Path(desktop_audio_receipt_path(cfg)).parent
            ),
        }
        body.update(native_helper_capabilities())
        return body

    @app.get("/control/gpu")
    async def gpu() -> dict[str, object]:
        info = detect_gpu_fn()
        return {
            "available": info.available,
            "device": info.device,
            "device_count": info.device_count,
            "device_indices": list(range(info.device_count)),
            "backend": info.backend,
            "reason": info.reason,
            "accelerators": list(getattr(info, "accelerators", ())),
            "engines": list(getattr(info, "engines", ())),
            "recommended_engine": getattr(info, "recommended_engine", "faster_whisper"),
            "gpus": nvidia_memory() if info.device == "cuda" else [],
        }

    @app.post("/control/start")
    async def start(request: Request) -> dict[str, object]:
        payload = await read_json(request)
        settings = merge_settings(state.settings, payload, require_profile=True)
        stop_client_fn(state.client_process)
        state.client_process = None
        close_process_log(state, clear_session=False)
        if process_running_fn(state.process):
            stop_service_fn(state.process)
        state.settings = settings
        session_id = ensure_process_session(cfg, state)
        state.process = start_service_fn(cfg, settings, session_id=session_id)
        append_stream_log(state, f"service runtime flags: no_vad={'on' if settings.no_vad else 'off'}")
        if bool(payload.get("start_stream", False)):
            stream_settings = merge_stream_settings(state.stream_settings, payload)
            wait_for_service_health(cfg.service_host, cfg.service_port, timeout_s=6.0)
            state.stream_settings = stream_settings
            state.client_process = start_client_fn(cfg, stream_settings)
            append_stream_log(
                state,
                f"starting: what client --local --input {stream_settings.input_mode} --host {cfg.service_host} --port {cfg.service_port}",
            )
            append_stream_log(
                state,
                f"client runtime flags: captions_on=forced event_prefix={stream_settings.event_prefix or ''}",
            )
            start_stream_log_pump(state, state.client_process)
        persist_settings(cfg, state)
        return {"ok": True}

    @app.post("/control/stop")
    async def stop() -> dict[str, object]:
        stop_client_fn(state.client_process)
        state.client_process = None
        try:
            desktop_audio_manager_mod.uninstall(
                repo_root, Path(desktop_audio_receipt_path(cfg))
            )
            append_stream_log(state, "ui: desktop manager api: auto-uninstall complete")
        except Exception as exc:
            append_stream_log(state, f"ui: desktop manager api: auto-uninstall error ({exc})")
        close_process_log(state, clear_session=True)
        stop_service_fn(state.process)
        state.process = None
        return {"ok": True}

    @app.post("/control/apply")
    async def apply(request: Request) -> dict[str, object]:
        payload = await read_json(request)
        settings = merge_settings(state.settings, payload, require_profile=False)
        stop_client_fn(state.client_process)
        state.client_process = None
        close_process_log(state, clear_session=False)
        if process_running_fn(state.process):
            stop_service_fn(state.process)
        state.settings = settings
        session_id = ensure_process_session(cfg, state)
        state.process = start_service_fn(cfg, settings, session_id=session_id)
        append_stream_log(state, f"service runtime flags: no_vad={'on' if settings.no_vad else 'off'}")
        persist_settings(cfg, state)
        return {"ok": True}

    @app.post("/control/settings")
    async def control_settings(request: Request) -> dict[str, object]:
        payload = await read_json(request)
        settings = merge_settings(state.settings, payload, require_profile=False)
        state.settings = settings
        persist_settings(cfg, state)
        append_stream_log(
            state,
            f"control settings updated: no_vad={'on' if settings.no_vad else 'off'} (service restart not required)",
        )
        return {
            "ok": True,
            "no_vad": bool(settings.no_vad),
            "publish_delay_seconds": int(settings.publish_delay_seconds),
            "boundary_candidate_points": int(settings.boundary_candidate_points),
            "overlay_width_px": int(settings.overlay_width_px),
            "overlay_height_px": int(settings.overlay_height_px),
            "overlay_padding_px": int(settings.overlay_padding_px),
            "overlay_font_size_px": float(settings.overlay_font_size_px),
            "gpu_mem_budget_mb": int(settings.gpu_mem_budget_mb),
        }

    @app.post("/control/publish-delay")
    async def publish_delay(request: Request) -> dict[str, object]:
        payload = await read_json(request)
        raw = payload.get("publish_delay_seconds", state.settings.publish_delay_seconds)
        try:
            delay = int(raw)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="publish_delay_seconds must be int") from exc
        delay = max(0, min(90, delay))
        state.settings.publish_delay_seconds = delay
        persist_settings(cfg, state)
        return {"ok": True, "publish_delay_seconds": delay}

    @app.post("/control/overlay-geometry")
    async def overlay_geometry(request: Request) -> dict[str, object]:
        payload = await read_json(request)
        s = state.settings
        width = clamp_int(
            payload.get("overlay_width_px", payload.get("width", s.overlay_width_px)),
            100,
            8192,
            s.overlay_width_px,
        )
        height = clamp_int(
            payload.get("overlay_height_px", payload.get("height", s.overlay_height_px)),
            60,
            8192,
            s.overlay_height_px,
        )
        pad = clamp_int(
            payload.get("overlay_padding_px", payload.get("padding", s.overlay_padding_px)),
            0,
            1024,
            s.overlay_padding_px,
        )
        max_pad = max(0, min(width // 2, height // 2) - 1)
        pad = min(pad, max_pad)
        font = clamp_float(
            payload.get("overlay_font_size_px", payload.get("font_size", s.overlay_font_size_px)),
            0.1,
            512.0,
            s.overlay_font_size_px,
        )
        s.overlay_width_px = width
        s.overlay_height_px = height
        s.overlay_padding_px = pad
        s.overlay_font_size_px = font
        persist_settings(cfg, state)
        return {
            "ok": True,
            "overlay_width_px": width,
            "overlay_height_px": height,
            "overlay_padding_px": pad,
            "overlay_font_size_px": font,
        }

    @app.post("/control/session/log")
    async def session_log(request: Request) -> dict[str, object]:
        payload = await read_json(request)
        message = str(payload.get("message") or "").strip()
        session_id = ensure_process_session(cfg, state)
        if message:
            append_stream_log(state, f"ui: {message}", count_for_heartbeat=False)
        return {"ok": True, "session_id": session_id, "process_log_path": state.process_log_path or ""}
