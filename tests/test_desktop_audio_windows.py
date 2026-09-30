"""Windows (WASAPI/DirectShow loopback) desktop-capture argument logic."""
import what.desktop_audio as da


_LIST_DEVICES_SECTIONED = """\
[dshow @ 0000] DirectShow video devices (some may be both video and audio devices)
[dshow @ 0000]  "HD WebCam"
[dshow @ 0000]     Alternative name "@device_pnp_\\\\?\\usb#vid"
[dshow @ 0000] DirectShow audio devices
[dshow @ 0000]  "Microphone (Realtek Audio)"
[dshow @ 0000]     Alternative name "@device_cm_{guid}\\Microphone"
[dshow @ 0000]  "Stereo Mix (Realtek Audio)"
[dshow @ 0000]     Alternative name "@device_cm_{guid}\\Stereo Mix"
"""

_LIST_DEVICES_TAGGED = """\
[dshow @ 0000]  "Microphone (Realtek Audio)" (audio)
[dshow @ 0000]  "CABLE Output (VB-Audio Virtual Cable)" (audio)
"""


def test_parse_dshow_sectioned_layout():
    devs = da._parse_dshow_audio_devices(_LIST_DEVICES_SECTIONED)
    assert devs == ["Microphone (Realtek Audio)", "Stereo Mix (Realtek Audio)"]
    # The webcam (video section) and @device alt-names are excluded.
    assert "HD WebCam" not in devs


def test_parse_dshow_tagged_layout():
    devs = da._parse_dshow_audio_devices(_LIST_DEVICES_TAGGED)
    assert devs == ["Microphone (Realtek Audio)", "CABLE Output (VB-Audio Virtual Cable)"]


def test_default_loopback_prefers_known_devices():
    devs = ["Microphone (Realtek Audio)", "Stereo Mix (Realtek Audio)"]
    assert da._windows_default_loopback(devs) == "Stereo Mix (Realtek Audio)"
    assert da._windows_default_loopback(["CABLE Output (VB-Audio Virtual Cable)"]) \
        == "CABLE Output (VB-Audio Virtual Cable)"
    assert da._windows_default_loopback(["Microphone (Realtek Audio)"]) is None


def test_wasapi_args_with_explicit_device():
    args = da.build_desktop_input_args("wasapi", "CABLE Output (VB-Audio Virtual Cable)")
    assert args == ["-f", "dshow", "-i", "audio=CABLE Output (VB-Audio Virtual Cable)"]


def test_wasapi_args_auto_selects_loopback(monkeypatch):
    monkeypatch.setattr(da, "_dshow_audio_devices",
                        lambda: ["Microphone (Realtek Audio)", "Stereo Mix (Realtek Audio)"])
    args = da.build_desktop_input_args("wasapi", "default")
    assert args == ["-f", "dshow", "-i", "audio=Stereo Mix (Realtek Audio)"]


def test_wasapi_no_loopback_raises_actionable(monkeypatch):
    monkeypatch.setattr(da, "_dshow_audio_devices", lambda: ["Microphone (Realtek Audio)"])
    try:
        da.build_desktop_input_args("wasapi", "default")
    except ValueError as exc:
        assert "Stereo Mix" in str(exc) or "VB-Cable" in str(exc)
    else:
        raise AssertionError("expected ValueError when no loopback device is present")


def test_list_desktop_devices_wasapi(monkeypatch):
    monkeypatch.setattr(da, "_dshow_audio_devices",
                        lambda: ["Microphone (Realtek Audio)", "Stereo Mix (Realtek Audio)"])
    assert da.list_desktop_devices("wasapi") == \
        ["Microphone (Realtek Audio)", "Stereo Mix (Realtek Audio)"]
