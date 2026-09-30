import json

from what.controller import controller_settings_store as css
from what.controller.state import ControllerState
from what.controller.types import ControllerConfig


def _cfg(tmp_path):
    return ControllerConfig(
        host="127.0.0.1",
        port=8780,
        service_host="127.0.0.1",
        service_port=8765,
        config_path=None,
        settings_path=str(tmp_path / "controller_settings.json"),
    )


def test_load_persisted_settings_ignores_malformed_json(tmp_path):
    cfg = _cfg(tmp_path)
    state = ControllerState()
    original_profile = state.settings.profile
    path = tmp_path / "controller_settings.json"
    path.write_text("{bad json", encoding="utf-8")

    css.load_persisted_settings(cfg, state)
    assert state.settings.profile == original_profile


def test_load_persisted_settings_partial_payload(tmp_path):
    cfg = _cfg(tmp_path)
    state = ControllerState()
    path = tmp_path / "controller_settings.json"
    path.write_text(
        json.dumps(
            {
                "control": {
                    "profile": "cpu_friendly",
                    "overlay_width_px": 9999,
                    "overlay_height_px": 10,
                    "overlay_padding_px": -4,
                    "overlay_font_size_px": 9999,
                }
            }
        ),
        encoding="utf-8",
    )

    css.load_persisted_settings(cfg, state)
    assert state.settings.profile == "cpu_friendly"
    assert state.settings.overlay_width_px == 8192
    assert state.settings.overlay_height_px == 60
    assert state.settings.overlay_padding_px == 0
    assert state.settings.overlay_font_size_px == 512.0


def test_settings_round_trip_persist_and_load(tmp_path):
    cfg = _cfg(tmp_path)
    state = ControllerState()
    state.settings.profile = "paragraph"
    state.settings.publish_delay_seconds = 12
    state.settings.no_vad = False
    state.settings.boundary_candidate_points = 5
    state.stream_settings.input_mode = "desktop"
    state.stream_settings.mic_enabled = False
    state.stream_settings.desktop_output_target = "what-desktop"
    state.stream_settings.desktop_capture_input = ":1"
    state.stream_settings.desktop_device = ":1"

    css.persist_settings(cfg, state)
    reloaded = ControllerState()
    css.load_persisted_settings(cfg, reloaded)

    assert reloaded.settings.profile == "paragraph"
    assert reloaded.settings.publish_delay_seconds == 12
    assert reloaded.settings.no_vad is False
    assert reloaded.settings.boundary_candidate_points == 5
    assert reloaded.stream_settings.input_mode == "desktop"
    assert reloaded.stream_settings.mic_enabled is False
    assert reloaded.stream_settings.desktop_output_target == "what-desktop"
    assert reloaded.stream_settings.desktop_capture_input == ":1"
    assert reloaded.stream_settings.desktop_device == ":1"


def test_load_legacy_stream_desktop_device_maps_to_capture_input(tmp_path):
    cfg = _cfg(tmp_path)
    state = ControllerState()
    path = tmp_path / "controller_settings.json"
    path.write_text(
        json.dumps(
            {
                "stream": {
                    "input_mode": "desktop",
                    "desktop_enabled": True,
                    "desktop_backend": "avfoundation",
                    "desktop_device": ":9",
                }
            }
        ),
        encoding="utf-8",
    )

    css.load_persisted_settings(cfg, state)
    assert state.stream_settings.desktop_capture_input == ":9"
    assert state.stream_settings.desktop_device == ":9"


def test_load_persisted_settings_clamps_boundary_candidate_points(tmp_path):
    cfg = _cfg(tmp_path)
    state = ControllerState()
    path = tmp_path / "controller_settings.json"
    path.write_text(
        json.dumps(
            {
                "control": {
                    "profile": "cpu_friendly",
                    "boundary_candidate_points": 0,
                }
            }
        ),
        encoding="utf-8",
    )

    css.load_persisted_settings(cfg, state)
    assert state.settings.boundary_candidate_points == 1


def test_migrate_stream_payload_prefers_dual_role_capture_over_legacy_alias():
    current = ControllerState().stream_settings
    migrated = css.migrate_stream_payload(
        {
            "input_mode": "desktop",
            "desktop_capture_input": ":4",
            "desktop_device": ":9",
            "desktop_output_target": "what-desktop",
        },
        current,
    )
    assert migrated.desktop_capture_input == ":4"
    assert migrated.desktop_device == ":4"
    assert migrated.desktop_output_target == "what-desktop"
