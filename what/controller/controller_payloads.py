from __future__ import annotations

from fastapi import HTTPException

from .state import ControlSettings, StreamSettings


async def read_json(request) -> dict:
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    return payload if isinstance(payload, dict) else {}


def merge_settings(
    current: ControlSettings,
    payload: dict,
    *,
    require_profile: bool,
    clamp_int,
    clamp_float,
) -> ControlSettings:
    profile = payload.get("profile") or current.profile
    if require_profile and not profile:
        raise HTTPException(status_code=400, detail="profile is required")
    return ControlSettings(
        profile=profile,
        engine=payload.get("engine") or current.engine,
        device=payload.get("device") or current.device,
        device_index=payload.get("device_index") or current.device_index,
        compute_type=payload.get("compute_type") or current.compute_type,
        model_size=payload.get("model_size") or current.model_size,
        beam_size=payload.get("beam_size") or current.beam_size,
        language=payload.get("language") or current.language,
        no_vad=bool(payload.get("no_vad", current.no_vad)),
        publish_delay_seconds=int(payload.get("publish_delay_seconds", current.publish_delay_seconds)),
        boundary_candidate_points=clamp_int(
            payload.get("boundary_candidate_points", current.boundary_candidate_points),
            1,
            7,
            current.boundary_candidate_points,
        ),
        overlay_width_px=clamp_int(payload.get("overlay_width_px", current.overlay_width_px), 100, 8192, current.overlay_width_px),
        overlay_height_px=clamp_int(payload.get("overlay_height_px", current.overlay_height_px), 60, 8192, current.overlay_height_px),
        overlay_padding_px=clamp_int(payload.get("overlay_padding_px", current.overlay_padding_px), 0, 1024, current.overlay_padding_px),
        overlay_font_size_px=clamp_float(payload.get("overlay_font_size_px", current.overlay_font_size_px), 0.1, 512.0, current.overlay_font_size_px),
        gpu_mem_budget_mb=clamp_int(payload.get("gpu_mem_budget_mb", current.gpu_mem_budget_mb), 0, 262144, current.gpu_mem_budget_mb),
    )


def merge_stream_settings(current: StreamSettings, payload: dict) -> StreamSettings:
    mode = payload.get("input_mode", current.input_mode)
    if mode not in ("mic", "file", "stdin", "desktop"):
        mode = current.input_mode or "mic"
    file_path = payload.get("file_path", current.file_path)
    if file_path is not None and not str(file_path).strip():
        file_path = None
    # Stage-5 policy:
    # - writable authorities are desktop_capture_input + desktop_output_target
    # - desktop_device remains read-only compatibility alias
    desktop_device_legacy = current.desktop_device
    desktop_capture_input = (
        payload.get("desktop_capture_input")
        or current.desktop_capture_input
        or desktop_device_legacy
    )
    desktop_output_target = (
        payload.get("desktop_output_target")
        or current.desktop_output_target
    )
    return StreamSettings(
        input_mode=mode,
        file_path=file_path,
        realtime=bool(payload.get("realtime", current.realtime)),
        mic_enabled=bool(payload.get("mic_enabled", current.mic_enabled)),
        mic_backend=payload.get("mic_backend") or current.mic_backend,
        mic_device=payload.get("mic_device") or current.mic_device,
        desktop_enabled=bool(payload.get("desktop_enabled", current.desktop_enabled)),
        desktop_backend=payload.get("desktop_backend") or current.desktop_backend,
        desktop_device=desktop_capture_input,
        desktop_output_target=desktop_output_target,
        desktop_capture_input=desktop_capture_input,
        event_prefix=payload.get("event_prefix", current.event_prefix),
    )
