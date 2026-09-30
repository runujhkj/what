"""Windows microphone capture via ffmpeg DirectShow."""
from types import SimpleNamespace

import pytest

from what import desktop_audio
from what.live_audio import build_live_ffmpeg_sections


def test_default_picks_first_non_loopback_input():
    devices = ["Stereo Mix (Realtek(R) Audio)", "Microphone (USBAudio2.0)"]
    args = desktop_audio.build_dshow_mic_args("default", devices)
    assert args == ["-f", "dshow", "-audio_buffer_size", "50", "-i", "audio=Microphone (USBAudio2.0)"]


def test_named_device_is_used_verbatim():
    args = desktop_audio.build_dshow_mic_args("Headset Microphone (Jabra)", [])
    assert args[-1] == "audio=Headset Microphone (Jabra)"


def test_no_microphone_raises_actionable_error():
    with pytest.raises(ValueError, match="No microphone found"):
        desktop_audio.build_dshow_mic_args("default", ["Stereo Mix (Realtek(R) Audio)"])


def test_mic_list_orders_microphones_before_loopback(monkeypatch):
    monkeypatch.setattr(desktop_audio, "_dshow_audio_devices",
                        lambda: ["Stereo Mix (Realtek)", "Microphone (USB)"])
    assert desktop_audio.list_dshow_mic_devices() == ["Microphone (USB)", "Stereo Mix (Realtek)"]


def test_live_sections_route_dshow_backend(monkeypatch):
    monkeypatch.setattr(desktop_audio, "_dshow_audio_devices", lambda: ["Microphone (USB)"])
    cfg = SimpleNamespace(mode="mic", mic_enabled=True, desktop_enabled=False,
                          mic_backend="dshow", mic_device="default")
    sections, _ = build_live_ffmpeg_sections(cfg)
    assert sections[-1] == "audio=Microphone (USB)"


@pytest.mark.parametrize("system,expected", [("Windows", "dshow"), ("Linux", "pulse"), ("Darwin", "avfoundation")])
def test_default_mic_backend_per_platform(monkeypatch, system, expected):
    monkeypatch.setattr(desktop_audio.platform, "system", lambda: system)
    assert desktop_audio.default_mic_backend() == expected
