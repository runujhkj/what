from __future__ import annotations

import json
import os
from pathlib import Path

from .state import ControlSettings, StreamSettings


def settings_store_path(cfg) -> str:
    custom = (cfg.settings_path or "").strip() if cfg.settings_path else ""
    if custom:
        return custom
    return os.path.join(os.path.expanduser("~"), ".what", "controller_settings.json")


def desktop_audio_receipt_path(cfg) -> str:
    settings_path = Path(settings_store_path(cfg))
    return str(settings_path.parent / "controller_desktop_audio_receipt.json")


def as_int_or_none(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except Exception:
        return None


def as_str_or_none(value):
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def migrate_stream_payload(stream: dict, current: StreamSettings) -> StreamSettings:
    mode = stream.get("input_mode", current.input_mode)
    if mode not in ("mic", "file", "stdin", "desktop"):
        mode = current.input_mode

    legacy_device = as_str_or_none(stream.get("desktop_device"))
    desktop_capture_input = as_str_or_none(stream.get("desktop_capture_input")) or legacy_device
    desktop_output_target = as_str_or_none(stream.get("desktop_output_target"))

    return StreamSettings(
        input_mode=mode,
        file_path=as_str_or_none(stream.get("file_path")),
        realtime=bool(stream.get("realtime", current.realtime)),
        mic_enabled=bool(stream.get("mic_enabled", current.mic_enabled)),
        mic_backend=as_str_or_none(stream.get("mic_backend")),
        mic_device=as_str_or_none(stream.get("mic_device")),
        desktop_enabled=bool(stream.get("desktop_enabled", current.desktop_enabled)),
        desktop_backend=as_str_or_none(stream.get("desktop_backend")),
        # Keep compatibility alias mirrored from capture authority.
        desktop_device=desktop_capture_input,
        desktop_output_target=desktop_output_target,
        desktop_capture_input=desktop_capture_input,
        event_prefix=stream.get("event_prefix", current.event_prefix),
    )


def clamp_int(value, min_value: int, max_value: int, fallback: int) -> int:
    try:
        iv = int(value)
    except Exception:
        iv = int(fallback)
    return max(min_value, min(max_value, iv))


def clamp_float(value, min_value: float, max_value: float, fallback: float) -> float:
    try:
        fv = float(value)
    except Exception:
        fv = float(fallback)
    return max(min_value, min(max_value, fv))


def persist_settings(cfg, state) -> None:
    try:
        path = settings_store_path(cfg)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        payload = {
            "version": 1,
            "control": {
                "profile": state.settings.profile,
                "engine": state.settings.engine,
                "device": state.settings.device,
                "device_index": state.settings.device_index,
                "compute_type": state.settings.compute_type,
                "model_size": state.settings.model_size,
                "beam_size": state.settings.beam_size,
                "language": state.settings.language,
                "no_vad": bool(state.settings.no_vad),
                "publish_delay_seconds": int(state.settings.publish_delay_seconds),
                "boundary_candidate_points": int(state.settings.boundary_candidate_points),
                "overlay_width_px": int(state.settings.overlay_width_px),
                "overlay_height_px": int(state.settings.overlay_height_px),
                "overlay_padding_px": int(state.settings.overlay_padding_px),
                "overlay_font_size_px": float(state.settings.overlay_font_size_px),
                "gpu_mem_budget_mb": int(state.settings.gpu_mem_budget_mb),
            },
            "stream": {
                "input_mode": state.stream_settings.input_mode,
                "file_path": state.stream_settings.file_path,
                "realtime": bool(state.stream_settings.realtime),
                "mic_enabled": bool(state.stream_settings.mic_enabled),
                "mic_backend": state.stream_settings.mic_backend,
                "mic_device": state.stream_settings.mic_device,
                "desktop_enabled": bool(state.stream_settings.desktop_enabled),
                "desktop_backend": state.stream_settings.desktop_backend,
                # Persist legacy alias as a mirror only (read-only compatibility window).
                "desktop_device": state.stream_settings.desktop_capture_input
                or state.stream_settings.desktop_device,
                "desktop_output_target": state.stream_settings.desktop_output_target,
                "desktop_capture_input": state.stream_settings.desktop_capture_input,
                "event_prefix": state.stream_settings.event_prefix,
            },
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
    except Exception:
        return


def load_persisted_settings(cfg, state) -> None:
    path = settings_store_path(cfg)
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return
    if not isinstance(payload, dict):
        return
    control = payload.get("control")
    if isinstance(control, dict):
        state.settings = ControlSettings(
            profile=as_str_or_none(control.get("profile")),
            engine=as_str_or_none(control.get("engine")),
            device=as_str_or_none(control.get("device")),
            device_index=as_int_or_none(control.get("device_index")),
            compute_type=as_str_or_none(control.get("compute_type")),
            model_size=as_str_or_none(control.get("model_size")),
            beam_size=as_int_or_none(control.get("beam_size")),
            language=as_str_or_none(control.get("language")),
            no_vad=bool(control.get("no_vad", state.settings.no_vad)),
            publish_delay_seconds=max(
                0, min(90, int(control.get("publish_delay_seconds", state.settings.publish_delay_seconds)))
            ),
            boundary_candidate_points=clamp_int(
                control.get("boundary_candidate_points", state.settings.boundary_candidate_points),
                1,
                7,
                state.settings.boundary_candidate_points,
            ),
            overlay_width_px=clamp_int(
                control.get("overlay_width_px", state.settings.overlay_width_px),
                100,
                8192,
                state.settings.overlay_width_px,
            ),
            overlay_height_px=clamp_int(
                control.get("overlay_height_px", state.settings.overlay_height_px),
                60,
                8192,
                state.settings.overlay_height_px,
            ),
            overlay_padding_px=clamp_int(
                control.get("overlay_padding_px", state.settings.overlay_padding_px),
                0,
                1024,
                state.settings.overlay_padding_px,
            ),
            overlay_font_size_px=clamp_float(
                control.get("overlay_font_size_px", state.settings.overlay_font_size_px),
                0.1,
                512.0,
                state.settings.overlay_font_size_px,
            ),
            gpu_mem_budget_mb=clamp_int(
                control.get("gpu_mem_budget_mb", state.settings.gpu_mem_budget_mb),
                0,
                262144,
                state.settings.gpu_mem_budget_mb,
            ),
        )
    stream = payload.get("stream")
    if isinstance(stream, dict):
        state.stream_settings = migrate_stream_payload(stream, state.stream_settings)
