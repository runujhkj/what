from fastapi.testclient import TestClient
import json

from what.controller.api import create_controller_app
from what.controller.state import ControllerState
from what.controller.types import ControllerConfig


class DummyProc:
    def __init__(self):
        self._running = True

    def poll(self):
        return None if self._running else 0


def test_controller_status_and_start(monkeypatch):
    cfg = ControllerConfig(
        host="127.0.0.1",
        port=8780,
        service_host="127.0.0.1",
        service_port=8765,
        config_path=None,
    )
    state = ControllerState()

    def fake_start_service(_cfg, _settings, session_id=None):
        _ = session_id
        return DummyProc()

    def fake_stop_service(_proc):
        return None

    def fake_start_client(_cfg, _settings):
        return DummyProc()

    def fake_stop_client(_proc):
        return None

    def fake_process_running(_proc):
        return _proc is not None

    monkeypatch.setattr("what.controller.api.start_service", fake_start_service)
    monkeypatch.setattr("what.controller.api.stop_service", fake_stop_service)
    monkeypatch.setattr("what.controller.api.start_client", fake_start_client)
    monkeypatch.setattr("what.controller.api.stop_client", fake_stop_client)
    monkeypatch.setattr("what.controller.api.process_running", fake_process_running)
    monkeypatch.setattr("what.controller.api._wait_for_service_health", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("what.controller.api._start_stream_log_pump", lambda *_args, **_kwargs: None)

    app = create_controller_app(cfg, state)
    client = TestClient(app)

    resp = client.get("/control/status")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["running"] is False
    assert payload["service_host"] == "127.0.0.1"
    assert payload["service_port"] == 8765
    assert payload["no_vad"] is True
    assert payload["boundary_candidate_points"] == 3

    resp = client.post("/control/start", json={"profile": "cpu_friendly"})
    assert resp.status_code == 200

    resp = client.get("/control/status")
    assert resp.status_code == 200
    assert resp.json()["running"] is True


def test_controller_apply_and_stop(monkeypatch):
    cfg = ControllerConfig(
        host="127.0.0.1",
        port=8780,
        service_host="127.0.0.1",
        service_port=8765,
        config_path=None,
    )
    state = ControllerState()

    def fake_start_service(_cfg, _settings, session_id=None):
        _ = session_id
        return DummyProc()

    def fake_stop_service(_proc):
        return None

    def fake_start_client(_cfg, _settings):
        return DummyProc()

    def fake_stop_client(_proc):
        return None

    def fake_process_running(_proc):
        return _proc is not None

    monkeypatch.setattr("what.controller.api.start_service", fake_start_service)
    monkeypatch.setattr("what.controller.api.stop_service", fake_stop_service)
    monkeypatch.setattr("what.controller.api.start_client", fake_start_client)
    monkeypatch.setattr("what.controller.api.stop_client", fake_stop_client)
    monkeypatch.setattr("what.controller.api.process_running", fake_process_running)
    monkeypatch.setattr("what.controller.api._wait_for_service_health", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("what.controller.api._start_stream_log_pump", lambda *_args, **_kwargs: None)

    app = create_controller_app(cfg, state)
    client = TestClient(app)

    resp = client.post("/control/start", json={"profile": "cpu_friendly"})
    assert resp.status_code == 200

    resp = client.post("/control/apply", json={"profile": "paragraph"})
    assert resp.status_code == 200

    resp = client.post("/control/stop")
    assert resp.status_code == 200

    resp = client.get("/control/status")
    assert resp.status_code == 200
    assert resp.json()["running"] is False


def test_controller_gpu_endpoint(monkeypatch):
    cfg = ControllerConfig(
        host="127.0.0.1",
        port=8780,
        service_host="127.0.0.1",
        service_port=8765,
        config_path=None,
    )
    state = ControllerState()

    class DummyGpu:
        available = True
        device = "cuda"
        device_count = 2
        backend = "ctranslate2"
        reason = "ok"

    monkeypatch.setattr("what.controller.api.detect_gpu", lambda: DummyGpu())

    app = create_controller_app(cfg, state)
    client = TestClient(app)
    resp = client.get("/control/gpu")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["available"] is True
    assert payload["device_count"] == 2
    assert payload["device_indices"] == [0, 1]


def test_controller_settings_persist_and_reload(monkeypatch, tmp_path):
    settings_path = tmp_path / "controller_settings.json"
    cfg = ControllerConfig(
        host="127.0.0.1",
        port=8780,
        service_host="127.0.0.1",
        service_port=8765,
        config_path=None,
        settings_path=str(settings_path),
    )
    state = ControllerState()

    def fake_start_service(_cfg, _settings, session_id=None):
        _ = session_id
        return DummyProc()

    def fake_stop_service(_proc):
        return None

    def fake_start_client(_cfg, _settings):
        return DummyProc()

    def fake_stop_client(_proc):
        return None

    def fake_process_running(_proc):
        return _proc is not None

    monkeypatch.setattr("what.controller.api.start_service", fake_start_service)
    monkeypatch.setattr("what.controller.api.stop_service", fake_stop_service)
    monkeypatch.setattr("what.controller.api.start_client", fake_start_client)
    monkeypatch.setattr("what.controller.api.stop_client", fake_stop_client)
    monkeypatch.setattr("what.controller.api.process_running", fake_process_running)
    monkeypatch.setattr("what.controller.api._wait_for_service_health", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("what.controller.api._start_stream_log_pump", lambda *_args, **_kwargs: None)

    app = create_controller_app(cfg, state)
    client = TestClient(app)

    resp = client.post(
        "/control/apply",
        json={
            "profile": "cpu_friendly",
            "device": "cpu",
            "compute_type": "int8",
            "model_size": "small",
            "beam_size": 1,
            "language": "en",
            "no_vad": False,
            "publish_delay_seconds": 15,
            "boundary_candidate_points": 5,
        },
    )
    assert resp.status_code == 200

    stream_resp = client.post(
        "/control/stream/start",
        json={
            "input_mode": "file",
            "file_path": "/tmp/a.wav",
            "realtime": True,
            "event_prefix": "EVENT:",
        },
    )
    assert stream_resp.status_code == 200
    assert settings_path.exists()

    raw = json.loads(settings_path.read_text(encoding="utf-8"))
    assert raw["control"]["profile"] == "cpu_friendly"
    assert bool(raw["control"]["no_vad"]) is False
    assert int(raw["control"]["publish_delay_seconds"]) == 15
    assert int(raw["control"]["boundary_candidate_points"]) == 5
    assert raw["stream"]["input_mode"] == "file"
    assert raw["stream"]["file_path"] == "/tmp/a.wav"

    reloaded = ControllerState()
    create_controller_app(cfg, reloaded)
    assert reloaded.settings.profile == "cpu_friendly"
    assert reloaded.settings.no_vad is False
    assert reloaded.settings.publish_delay_seconds == 15
    assert reloaded.settings.boundary_candidate_points == 5
    assert reloaded.stream_settings.input_mode == "file"
    assert reloaded.stream_settings.file_path == "/tmp/a.wav"


def test_session_log_bootstrap_attaches_process_log_once(tmp_path):
    cfg = ControllerConfig(
        host="127.0.0.1",
        port=8780,
        service_host="127.0.0.1",
        service_port=8765,
        config_path=None,
        settings_path=str(tmp_path / "controller_settings.json"),
    )
    state = ControllerState()
    app = create_controller_app(cfg, state)
    client = TestClient(app)

    resp1 = client.post("/control/session/log", json={"message": "hello"})
    assert resp1.status_code == 200
    assert resp1.json()["ok"] is True
    first_heartbeat = float(state.stream_log_last_ts or 0.0)

    resp2 = client.post("/control/session/log", json={"message": "again"})
    assert resp2.status_code == 200
    assert resp2.json()["ok"] is True
    second_heartbeat = float(state.stream_log_last_ts or 0.0)

    lines = [line for _, line in state.stream_logs]
    attached = [x for x in lines if x.startswith("process log attached: ")]
    ui_lines = [x for x in lines if x.startswith("ui: ")]
    assert len(attached) == 1
    assert ui_lines == ["ui: hello", "ui: again"]
    assert second_heartbeat == first_heartbeat
