from what.controller.process import build_client_args, build_service_args
from what.controller.state import ControlSettings, StreamSettings
from what.controller.types import ControllerConfig


def test_build_service_args_smoke():
    cfg = ControllerConfig(
        host="127.0.0.1",
        port=8780,
        service_host="127.0.0.1",
        service_port=8765,
        config_path=None,
    )
    settings = ControlSettings(
        profile="cpu_friendly",
        device="cpu",
        compute_type="int8",
        model_size="small",
        beam_size=1,
        language="en",
    )
    args = build_service_args(cfg, settings)
    assert args[:3] == [args[0], "-m", "what"]
    assert "service" in args
    assert "--profile" in args
    assert "cpu_friendly" in args
    assert "--no-vad" in args
    assert "--boundary-candidate-points" in args
    idx = args.index("--boundary-candidate-points")
    assert args[idx + 1] == "3"


def test_build_service_args_respects_no_vad_toggle_off():
    cfg = ControllerConfig(
        host="127.0.0.1",
        port=8780,
        service_host="127.0.0.1",
        service_port=8765,
        config_path=None,
    )
    settings = ControlSettings(profile="cpu_friendly", no_vad=False)
    args = build_service_args(cfg, settings)
    assert "--no-vad" not in args


def test_build_client_args_mixed_capture():
    cfg = ControllerConfig(
        host="127.0.0.1",
        port=8780,
        service_host="127.0.0.1",
        service_port=8765,
        config_path=None,
    )
    settings = StreamSettings(
        input_mode="mic",
        mic_enabled=True,
        mic_backend="avfoundation",
        mic_device="default",
        desktop_enabled=True,
        desktop_backend="avfoundation",
        desktop_device="2: what-desktop",
        event_prefix="EVENT:",
    )
    args = build_client_args(cfg, settings)
    assert args[:3] == [args[0], "-m", "what"]
    assert "client" in args
    assert "--input" in args
    assert "mic" in args
    assert "--mic-enabled" in args
    assert "--desktop-enabled" in args
    assert "--no-mic" not in args
    assert "--no-desktop" not in args
    assert "--desktop-backend" in args
    assert "avfoundation" in args
    assert "--desktop-device" in args
    assert "2: what-desktop" in args


def test_build_client_args_prefers_desktop_capture_input_over_legacy_alias():
    cfg = ControllerConfig(
        host="127.0.0.1",
        port=8780,
        service_host="127.0.0.1",
        service_port=8765,
        config_path=None,
    )
    settings = StreamSettings(
        input_mode="desktop",
        desktop_enabled=True,
        desktop_backend="avfoundation",
        desktop_device=":1",
        desktop_capture_input=":3",
    )
    args = build_client_args(cfg, settings)
    idx = args.index("--desktop-device")
    assert args[idx + 1] == ":3"


def test_start_service_rejects_occupied_port_before_spawning(monkeypatch):
    import errno
    from unittest.mock import MagicMock
    import pytest
    from fastapi import HTTPException
    from what.controller.process import start_service

    probe = MagicMock()
    probe.__enter__.return_value = probe
    probe.bind.side_effect = OSError(errno.EADDRINUSE, "Address already in use")
    spawn = MagicMock()
    monkeypatch.setattr("what.controller.process.socket.socket", lambda *args: probe)
    monkeypatch.setattr("what.controller.process.subprocess.Popen", spawn)
    cfg = ControllerConfig(host="127.0.0.1", port=8780, service_host="127.0.0.1",
                           service_port=8765, config_path=None)
    with pytest.raises(HTTPException) as error:
        start_service(cfg, ControlSettings())
    assert error.value.status_code == 409
    assert "already in use" in error.value.detail
    spawn.assert_not_called()


def test_start_service_free_port_keeps_session_and_interpreter(monkeypatch):
    from unittest.mock import MagicMock
    from what.controller.process import start_service
    import sys

    probe = MagicMock()
    probe.__enter__.return_value = probe
    spawn = MagicMock()
    monkeypatch.setattr("what.controller.process.socket.socket", lambda *args: probe)
    monkeypatch.setattr("what.controller.process.subprocess.Popen", spawn)
    cfg = ControllerConfig(host="127.0.0.1", port=8780, service_host="127.0.0.1",
                           service_port=8765, config_path=None)
    start_service(cfg, ControlSettings(), session_id="new-session")
    probe.bind.assert_called_once_with(("127.0.0.1", 8765))
    assert spawn.call_args.args[0][:3] == [sys.executable, "-m", "what"]
    assert spawn.call_args.kwargs["env"]["WHAT_SESSION_ID"] == "new-session"
    import subprocess
    assert spawn.call_args.kwargs["stdin"] == subprocess.DEVNULL
