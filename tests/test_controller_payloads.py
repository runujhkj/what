import asyncio

import pytest
from fastapi import HTTPException

from what.controller import controller_payloads as cp
from what.controller.state import ControlSettings, StreamSettings


class _Req:
    def __init__(self, value=None, *, raises=False):
        self._value = value
        self._raises = raises

    async def json(self):
        if self._raises:
            raise RuntimeError("bad-json")
        return self._value


def test_read_json_non_dict_falls_back_to_empty():
    out = asyncio.run(cp.read_json(_Req(["not", "dict"])))
    assert out == {}


def test_read_json_exception_falls_back_to_empty():
    out = asyncio.run(cp.read_json(_Req(raises=True)))
    assert out == {}


def test_merge_stream_settings_invalid_mode_falls_back_to_current():
    current = StreamSettings(input_mode="desktop", file_path="/tmp/a.wav")
    out = cp.merge_stream_settings(current, {"input_mode": "invalid"})
    assert out.input_mode == "desktop"


def test_merge_stream_settings_blank_file_path_normalized_to_none():
    current = StreamSettings(input_mode="file", file_path="/tmp/a.wav")
    out = cp.merge_stream_settings(current, {"file_path": "   "})
    assert out.file_path is None


def test_merge_settings_requires_profile():
    current = ControlSettings(profile=None)
    with pytest.raises(HTTPException) as exc:
        cp.merge_settings(
            current,
            {},
            require_profile=True,
            clamp_int=lambda v, _min, _max, fallback: int(v if v is not None else fallback),
            clamp_float=lambda v, _min, _max, fallback: float(v if v is not None else fallback),
        )
    assert exc.value.status_code == 400
    assert "profile is required" in str(exc.value.detail)


def test_merge_settings_clamps_boundary_candidate_points():
    current = ControlSettings(profile="cpu_friendly", boundary_candidate_points=3)
    out = cp.merge_settings(
        current,
        {"boundary_candidate_points": 99},
        require_profile=False,
        clamp_int=lambda v, _min, _max, fallback: max(_min, min(_max, int(v if v is not None else fallback))),
        clamp_float=lambda v, _min, _max, fallback: float(v if v is not None else fallback),
    )
    assert out.boundary_candidate_points == 7


def test_merge_settings_respects_no_vad_false():
    current = ControlSettings(profile="cpu_friendly", no_vad=True)
    out = cp.merge_settings(
        current,
        {"no_vad": False},
        require_profile=False,
        clamp_int=lambda v, _min, _max, fallback: max(_min, min(_max, int(v if v is not None else fallback))),
        clamp_float=lambda v, _min, _max, fallback: float(v if v is not None else fallback),
    )
    assert out.no_vad is False


def test_merge_stream_settings_ignores_legacy_desktop_device_payload_writes():
    current = StreamSettings(input_mode="desktop", desktop_capture_input=":1", desktop_device=":1")
    out = cp.merge_stream_settings(current, {"desktop_device": ":3"})
    assert out.desktop_capture_input == ":1"
    assert out.desktop_device == ":1"


def test_merge_stream_settings_preserves_dual_role_fields():
    current = StreamSettings(
        input_mode="desktop",
        desktop_output_target="what-desktop",
        desktop_capture_input=":1",
        desktop_device=":1",
    )
    out = cp.merge_stream_settings(current, {"desktop_output_target": "what-desktop-2"})
    assert out.desktop_output_target == "what-desktop-2"
    assert out.desktop_capture_input == ":1"
    assert out.desktop_device == ":1"


def test_merge_stream_settings_updates_capture_input_from_dual_role_field():
    current = StreamSettings(input_mode="desktop", desktop_capture_input=":1", desktop_device=":1")
    out = cp.merge_stream_settings(current, {"desktop_capture_input": ":3"})
    assert out.desktop_capture_input == ":3"
    assert out.desktop_device == ":3"
