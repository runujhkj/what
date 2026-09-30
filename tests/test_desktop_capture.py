from what.desktop_capture import capture_command


def test_linux_capture_uses_monitor_and_fixed_pcm_format(monkeypatch):
    monkeypatch.setattr("what.desktop_audio._pactl_available", lambda: True)
    monkeypatch.setattr("what.desktop_audio._pulse_default_monitor", lambda: "output.monitor")
    command = capture_command(backend="pulse")
    assert command[command.index("-i") + 1] == "output.monitor"
    assert command[command.index("-ar") + 1] == "16000"
    assert command[command.index("-ac") + 1] == "1"


def test_pcm16_mono_downmixes_and_clips():
    import numpy as np
    from what.desktop_capture import to_pcm16_mono

    frames = np.array([[0.5, -0.5], [2.0, 2.0], [-1.0, -1.0]], dtype=np.float32)
    out = np.frombuffer(to_pcm16_mono(frames), "<i2")
    assert out.tolist() == [0, 32767, -32767]


def test_windows_default_device_uses_wasapi_loopback(monkeypatch):
    import what.desktop_capture as dc

    calls = []
    monkeypatch.setattr(dc.os, "name", "nt")
    monkeypatch.setattr(dc, "run_wasapi_loopback", lambda out: calls.append(out))
    monkeypatch.setattr(dc, "capture_command", lambda *a: (_ for _ in ()).throw(AssertionError("no ffmpeg")))
    monkeypatch.setattr(dc.sys, "argv", ["desktop_capture", "--device", "default"])
    dc.main()
    assert len(calls) == 1


def test_windows_named_device_uses_ffmpeg_dshow(monkeypatch):
    import what.desktop_capture as dc

    monkeypatch.setattr(dc.os, "name", "nt")
    monkeypatch.setattr(dc, "run_wasapi_loopback", lambda out: (_ for _ in ()).throw(AssertionError("no loopback")))
    monkeypatch.setattr("what.desktop_audio._dshow_audio_devices", lambda: [])
    # Explicit backend: patching os.name alone doesn't make platform.system() say Windows.
    monkeypatch.setattr(dc.sys, "argv", ["desktop_capture", "--device", "Stereo Mix (Realtek)",
                                         "--backend", "wasapi"])
    ran = []

    class FakeProc:
        def wait(self):
            return 0

    import subprocess
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: ran.append(cmd) or FakeProc())
    try:
        dc.main()
    except SystemExit:
        pass
    assert "audio=Stereo Mix (Realtek)" in ran[0]
