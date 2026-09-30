from fastapi.testclient import TestClient

from what.controller.api import create_controller_app
from what.controller.state import ControllerState
from what.controller.types import ControllerConfig


class DummyProc:
    def __init__(self):
        self._running = True

    def poll(self):
        return None if self._running else 0


def _cfg(tmp_path) -> ControllerConfig:
    return ControllerConfig(
        host="127.0.0.1",
        port=8780,
        service_host="127.0.0.1",
        service_port=8765,
        config_path=None,
        settings_path=str(tmp_path / "controller_settings.json"),
    )


def _patch_controller_runtime(monkeypatch):
    def fake_start_service(_cfg, _settings, session_id=None):
        _ = session_id
        return DummyProc()

    def fake_stop_service(_proc):
        return None

    def fake_stop_client(_proc):
        return None

    def fake_process_running(proc):
        return proc is not None and proc.poll() is None

    monkeypatch.setattr("what.controller.api.start_service", fake_start_service)
    monkeypatch.setattr("what.controller.api.stop_service", fake_stop_service)
    monkeypatch.setattr("what.controller.api.stop_client", fake_stop_client)
    monkeypatch.setattr("what.controller.api.process_running", fake_process_running)
    monkeypatch.setattr("what.controller.api._wait_for_service_health", lambda *_a, **_k: None)
    monkeypatch.setattr("what.controller.api._start_stream_log_pump", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "what.controller.routes_stream.list_desktop_devices",
        lambda _backend: ["0: what-desktop", "1: BlackHole 2ch", "2: Built-in Microphone"],
    )
    route = {
        "supported": True,
        "enabled": True,
        "ready": True,
        "name_expected": "what-desktop",
        "current_output": "what-desktop",
        "target_output": "what-desktop",
    }
    monkeypatch.setattr(
        "what.controller.routes_stream.audio_routing_manager.probe_routing",
        lambda state_dir=None: dict(route),
    )
    monkeypatch.setattr(
        "what.controller.routes_stream.audio_routing_manager.ensure_routing",
        lambda _repo_root, state_dir=None: {"ok": True, "changed": False, "routing": dict(route)},
    )


def test_stream_start_mixed_capture_passes_settings(monkeypatch, tmp_path):
    _patch_controller_runtime(monkeypatch)
    cfg = _cfg(tmp_path)
    state = ControllerState()
    seen = {}

    def fake_start_client(_cfg, settings):
        seen["input_mode"] = settings.input_mode
        seen["mic_enabled"] = bool(settings.mic_enabled)
        seen["mic_backend"] = settings.mic_backend
        seen["mic_device"] = settings.mic_device
        seen["desktop_enabled"] = bool(settings.desktop_enabled)
        seen["desktop_backend"] = settings.desktop_backend
        seen["desktop_device"] = settings.desktop_device
        return DummyProc()

    monkeypatch.setattr("what.controller.api.start_client", fake_start_client)

    app = create_controller_app(cfg, state)
    client = TestClient(app)

    payload = {
        "input_mode": "mic",
        "mic_enabled": True,
        "mic_backend": "avfoundation",
        "mic_device": "default",
        "desktop_enabled": True,
        "desktop_backend": "avfoundation",
        "desktop_output_target": "what-desktop",
        "desktop_capture_input": ":1",
        "event_prefix": "EVENT:",
    }
    resp = client.post("/control/stream/start", json=payload)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert seen == {
        "input_mode": "mic",
        "mic_enabled": True,
        "mic_backend": "avfoundation",
        "mic_device": ":2",
        "desktop_enabled": True,
        "desktop_backend": "avfoundation",
        "desktop_device": ":0",
    }

    status = client.get("/control/status")
    assert status.status_code == 200
    body = status.json()
    assert body["stream_input_mode"] == "mic"
    assert body["stream_mic_enabled"] is True
    assert body["stream_desktop_enabled"] is True
    assert body["stream_mic_device"] == ":2"
    assert body["stream_desktop_device"] == ":0"


def test_stream_start_supports_desktop_mode_with_mic_enabled(monkeypatch, tmp_path):
    _patch_controller_runtime(monkeypatch)
    cfg = _cfg(tmp_path)
    state = ControllerState()
    seen = {}

    def fake_start_client(_cfg, settings):
        seen["input_mode"] = settings.input_mode
        seen["mic_enabled"] = bool(settings.mic_enabled)
        seen["desktop_enabled"] = bool(settings.desktop_enabled)
        return DummyProc()

    monkeypatch.setattr("what.controller.api.start_client", fake_start_client)

    app = create_controller_app(cfg, state)
    client = TestClient(app)
    resp = client.post(
        "/control/stream/start",
        json={
            "input_mode": "desktop",
            "mic_enabled": True,
            "desktop_enabled": True,
            "desktop_backend": "avfoundation",
            "desktop_output_target": "what-desktop",
            "desktop_capture_input": ":1",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert seen["input_mode"] == "desktop"
    assert seen["mic_enabled"] is True
    assert seen["desktop_enabled"] is True


def test_stream_start_mixed_capture_emits_start_log(monkeypatch, tmp_path):
    _patch_controller_runtime(monkeypatch)
    cfg = _cfg(tmp_path)
    state = ControllerState()
    monkeypatch.setattr("what.controller.api.start_client", lambda *_a, **_k: DummyProc())

    app = create_controller_app(cfg, state)
    client = TestClient(app)
    resp = client.post(
        "/control/stream/start",
        json={
            "input_mode": "mic",
            "mic_enabled": True,
            "desktop_enabled": True,
            "desktop_backend": "avfoundation",
            "desktop_output_target": "what-desktop",
            "desktop_capture_input": ":1",
            "event_prefix": "EVENT:",
        },
    )
    assert resp.status_code == 200
    lines = [line for _, line in state.stream_logs]
    assert any("starting: what client --local --input mic" in line for line in lines)
