from fastapi.testclient import TestClient
import time

from what.controller.api import create_controller_app
from what.controller.state import ControllerState
from what.controller.types import ControllerConfig


class DummyProc:
    def __init__(self):
        self._running = True

    def poll(self):
        return None if self._running else 0


def _cfg() -> ControllerConfig:
    return ControllerConfig(
        host="127.0.0.1",
        port=8780,
        service_host="127.0.0.1",
        service_port=8765,
        config_path=None,
    )


def _patch_routing_ok(monkeypatch, *, current: str = "what-desktop", target: str = "what-desktop") -> None:
    route = {
        "supported": True,
        "enabled": True,
        "ready": True,
        "name_expected": "what-desktop",
        "current_output": current,
        "target_output": target,
    }
    monkeypatch.setattr(
        "what.controller.routes_stream.audio_routing_manager.probe_routing",
        lambda state_dir=None: dict(route),
    )
    monkeypatch.setattr(
        "what.controller.routes_stream.audio_routing_manager.ensure_routing",
        lambda _repo_root, state_dir=None: {"ok": True, "changed": False, "routing": dict(route)},
    )


def _patch_routing_unresolved(monkeypatch) -> None:
    route = {
        "supported": True,
        "enabled": True,
        "ready": False,
        "name_expected": "what-desktop",
        "current_output": "Built-in Output",
        "target_output": "Built-in Output",
    }
    monkeypatch.setattr(
        "what.controller.routes_stream.audio_routing_manager.probe_routing",
        lambda state_dir=None: dict(route),
    )
    monkeypatch.setattr(
        "what.controller.routes_stream.audio_routing_manager.ensure_routing",
        lambda _repo_root, state_dir=None: {"ok": False, "changed": False, "routing": dict(route)},
    )


def test_stream_start_stop_and_logs(monkeypatch):
    state = ControllerState()
    cfg = _cfg()

    def fake_start_service(_cfg, _settings, session_id=None):
        _ = session_id
        return DummyProc()

    def fake_start_client(_cfg, _settings):
        return DummyProc()

    def fake_stop_service(_proc):
        return None

    def fake_stop_client(_proc):
        return None

    def fake_process_running(proc):
        return proc is not None and proc.poll() is None

    monkeypatch.setattr("what.controller.api.start_service", fake_start_service)
    monkeypatch.setattr("what.controller.api.start_client", fake_start_client)
    monkeypatch.setattr("what.controller.api.stop_service", fake_stop_service)
    monkeypatch.setattr("what.controller.api.stop_client", fake_stop_client)
    monkeypatch.setattr("what.controller.api.process_running", fake_process_running)
    monkeypatch.setattr("what.controller.api._wait_for_service_health", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("what.controller.api._start_stream_log_pump", lambda *_args, **_kwargs: None)

    app = create_controller_app(cfg, state)
    client = TestClient(app)

    start_resp = client.post("/control/stream/start", json={"input_mode": "mic", "event_prefix": "EVENT:"})
    assert start_resp.status_code == 200
    assert start_resp.json()["ok"] is True

    status_resp = client.get("/control/status")
    assert status_resp.status_code == 200
    status_payload = status_resp.json()
    assert status_payload["running"] is True
    assert status_payload["stream_running"] is True
    assert status_payload["stream_input_mode"] == "mic"

    logs_resp = client.get("/control/stream/logs?offset=0")
    assert logs_resp.status_code == 200
    logs_payload = logs_resp.json()
    assert logs_payload["ok"] is True
    assert "server_now_sec" in logs_payload
    assert "last_event_sec" in logs_payload
    assert "event_idle_sec" in logs_payload
    assert "event_stalled" in logs_payload
    assert len(logs_payload["lines"]) >= 1
    assert any(
        "starting: what client --local --input mic" in row["line"]
        for row in logs_payload["lines"]
    )
    next_offset = logs_payload["next_offset"]

    logs_resp2 = client.get(f"/control/stream/logs?offset={next_offset}")
    assert logs_resp2.status_code == 200
    assert logs_resp2.json()["lines"] == []
    events_resp = client.get("/control/stream/events?offset=0")
    assert events_resp.status_code == 200
    events_payload = events_resp.json()
    assert events_payload["ok"] is True
    assert "events" in events_payload
    assert "event_stalled" in events_payload

    stop_resp = client.post("/control/stream/stop")
    assert stop_resp.status_code == 200
    assert stop_resp.json()["ok"] is True


def test_stream_logs_exposes_event_stall_metadata(monkeypatch):
    state = ControllerState()
    cfg = _cfg()

    def fake_start_service(_cfg, _settings, session_id=None):
        _ = session_id
        return DummyProc()

    def fake_start_client(_cfg, _settings):
        return DummyProc()

    def fake_stop_service(_proc):
        return None

    def fake_stop_client(_proc):
        return None

    def fake_process_running(proc):
        return proc is not None and proc.poll() is None

    monkeypatch.setattr("what.controller.api.start_service", fake_start_service)
    monkeypatch.setattr("what.controller.api.start_client", fake_start_client)
    monkeypatch.setattr("what.controller.api.stop_service", fake_stop_service)
    monkeypatch.setattr("what.controller.api.stop_client", fake_stop_client)
    monkeypatch.setattr("what.controller.api.process_running", fake_process_running)
    monkeypatch.setattr("what.controller.api._wait_for_service_health", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("what.controller.api._start_stream_log_pump", lambda *_args, **_kwargs: None)

    app = create_controller_app(cfg, state)
    client = TestClient(app)
    client.post("/control/stream/start", json={"input_mode": "mic", "event_prefix": "EVENT:"})

    # Simulate a stale event stream while client is still running.
    state.stream_log_last_ts = time.time() - 30.0
    with state.stream_log_lock:
        state.stream_logs.clear()

    offset = state.stream_log_seq
    from what.controller.controller_route_utils import append_stream_log
    append_stream_log(state, "event lane: reconnecting", count_for_heartbeat=False)
    resp = client.get(f"/control/stream/logs?offset={offset}")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["lines"]  # Diagnostic chatter must not conceal stale audio events.
    assert payload["ok"] is True
    assert payload["stream_running"] is True
    assert payload["event_idle_sec"] >= 2.0
    assert payload["event_stalled"] is True


def test_control_start_with_start_stream(monkeypatch):
    state = ControllerState()
    cfg = _cfg()

    def fake_start_service(_cfg, _settings, session_id=None):
        _ = session_id
        return DummyProc()

    def fake_start_client(_cfg, _settings):
        return DummyProc()

    def fake_stop_service(_proc):
        return None

    def fake_stop_client(_proc):
        return None

    def fake_process_running(proc):
        return proc is not None and proc.poll() is None

    monkeypatch.setattr("what.controller.api.start_service", fake_start_service)
    monkeypatch.setattr("what.controller.api.start_client", fake_start_client)
    monkeypatch.setattr("what.controller.api.stop_service", fake_stop_service)
    monkeypatch.setattr("what.controller.api.stop_client", fake_stop_client)
    monkeypatch.setattr("what.controller.api.process_running", fake_process_running)
    monkeypatch.setattr("what.controller.api._wait_for_service_health", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("what.controller.api._start_stream_log_pump", lambda *_args, **_kwargs: None)

    app = create_controller_app(cfg, state)
    client = TestClient(app)

    resp = client.post(
        "/control/start",
        json={"profile": "cpu_friendly", "start_stream": True, "input_mode": "mic", "event_prefix": "EVENT:"},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    status = client.get("/control/status").json()
    assert status["running"] is True
    assert status["stream_running"] is True


def test_stream_settings_disables_desktop_without_output_target(monkeypatch, tmp_path):
    state = ControllerState()
    cfg = _cfg()
    cfg.settings_path = str(tmp_path / "controller_settings.json")

    def fake_start_service(_cfg, _settings, session_id=None):
        _ = session_id
        return DummyProc()

    def fake_start_client(_cfg, _settings):
        return DummyProc()

    def fake_stop_service(_proc):
        return None

    def fake_stop_client(_proc):
        return None

    def fake_process_running(proc):
        return proc is not None and proc.poll() is None

    monkeypatch.setattr("what.controller.api.start_service", fake_start_service)
    monkeypatch.setattr("what.controller.api.start_client", fake_start_client)
    monkeypatch.setattr("what.controller.api.stop_service", fake_stop_service)
    monkeypatch.setattr("what.controller.api.stop_client", fake_stop_client)
    monkeypatch.setattr("what.controller.api.process_running", fake_process_running)
    monkeypatch.setattr("what.controller.api._wait_for_service_health", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("what.controller.api._start_stream_log_pump", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("what.controller.routes_stream.list_desktop_devices", lambda _backend: [])

    app = create_controller_app(cfg, state)
    client = TestClient(app)

    resp = client.post(
        "/control/stream/settings",
        json={
            "input_mode": "mic",
            "mic_enabled": False,
            "desktop_enabled": True,
            "desktop_backend": "avfoundation",
            "desktop_device": "",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["stream_mic_enabled"] is False
    assert body["stream_desktop_enabled"] is False
    assert body["stream_desktop_disabled_reason"] == "no_desktop_output_target"
    assert body["stream_desktop_output_resolved"] is False
    assert body["stream_desktop_capture_resolved"] is False


def test_stream_settings_legacy_desktop_device_echoes_dual_role_fields(monkeypatch):
    state = ControllerState()
    cfg = _cfg()

    monkeypatch.setattr("what.controller.api._wait_for_service_health", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("what.controller.api._start_stream_log_pump", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "what.controller.routes_stream.list_desktop_devices",
        lambda _backend: ["0: what-desktop", "1: BlackHole 2ch"],
    )

    app = create_controller_app(cfg, state)
    client = TestClient(app)

    resp = client.post(
        "/control/stream/settings",
        json={
            "input_mode": "desktop",
            "desktop_enabled": True,
            "desktop_backend": "avfoundation",
            "desktop_device": ":1",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["stream_desktop_enabled"] is True
    assert body["stream_desktop_output_target"] == "what-desktop"
    assert body["stream_desktop_capture_input"] == ":0"
    assert body["stream_desktop_output_resolved"] is True
    assert body["stream_desktop_capture_resolved"] is True
    assert body["stream_desktop_fallback_enabled"] is False


def test_stream_settings_disables_desktop_without_capture_input(monkeypatch):
    state = ControllerState()
    cfg = _cfg()

    monkeypatch.setattr("what.controller.api._wait_for_service_health", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("what.controller.api._start_stream_log_pump", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "what.controller.routes_stream.list_desktop_devices",
        lambda _backend: ["0: Speakers", "2: Built-in Microphone"],
    )

    app = create_controller_app(cfg, state)
    client = TestClient(app)

    resp = client.post(
        "/control/stream/settings",
        json={
            "input_mode": "desktop",
            "desktop_enabled": True,
            "desktop_backend": "avfoundation",
            "desktop_output_target": "Speakers",
            "desktop_capture_input": "",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["stream_desktop_enabled"] is False
    assert body["stream_desktop_disabled_reason"] == "no_desktop_capture_input"
    assert body["stream_desktop_output_resolved"] is True
    assert body["stream_desktop_capture_resolved"] is False


def test_stream_start_allows_both_sources_disabled(monkeypatch):
    state = ControllerState()
    cfg = _cfg()
    seen = {}

    def fake_start_service(_cfg, _settings, session_id=None):
        _ = session_id
        return DummyProc()

    def fake_start_client(_cfg, settings):
        seen["mic_enabled"] = bool(settings.mic_enabled)
        seen["desktop_enabled"] = bool(settings.desktop_enabled)
        return DummyProc()

    def fake_stop_service(_proc):
        return None

    def fake_stop_client(_proc):
        return None

    def fake_process_running(proc):
        return proc is not None and proc.poll() is None

    monkeypatch.setattr("what.controller.api.start_service", fake_start_service)
    monkeypatch.setattr("what.controller.api.start_client", fake_start_client)
    monkeypatch.setattr("what.controller.api.stop_service", fake_stop_service)
    monkeypatch.setattr("what.controller.api.stop_client", fake_stop_client)
    monkeypatch.setattr("what.controller.api.process_running", fake_process_running)
    monkeypatch.setattr("what.controller.api._wait_for_service_health", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("what.controller.api._start_stream_log_pump", lambda *_args, **_kwargs: None)

    app = create_controller_app(cfg, state)
    client = TestClient(app)

    resp = client.post(
        "/control/stream/start",
        json={
            "input_mode": "mic",
            "mic_enabled": False,
            "desktop_enabled": False,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["stream_mic_enabled"] is False
    assert body["stream_desktop_enabled"] is False
    assert seen == {"mic_enabled": False, "desktop_enabled": False}


def test_stream_start_rebinds_what_desktop_selector_to_loopback_capture(monkeypatch):
    state = ControllerState()
    cfg = _cfg()
    seen = {}

    def fake_start_service(_cfg, _settings, session_id=None):
        _ = session_id
        return DummyProc()

    def fake_start_client(_cfg, settings):
        seen["desktop_enabled"] = bool(settings.desktop_enabled)
        seen["desktop_backend"] = str(settings.desktop_backend or "")
        seen["desktop_device"] = str(settings.desktop_device or "")
        return DummyProc()

    def fake_stop_service(_proc):
        return None

    def fake_stop_client(_proc):
        return None

    def fake_process_running(proc):
        return proc is not None and proc.poll() is None

    monkeypatch.setattr("what.controller.api.start_service", fake_start_service)
    monkeypatch.setattr("what.controller.api.start_client", fake_start_client)
    monkeypatch.setattr("what.controller.api.stop_service", fake_stop_service)
    monkeypatch.setattr("what.controller.api.stop_client", fake_stop_client)
    monkeypatch.setattr("what.controller.api.process_running", fake_process_running)
    monkeypatch.setattr("what.controller.api._wait_for_service_health", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("what.controller.api._start_stream_log_pump", lambda *_args, **_kwargs: None)
    _patch_routing_ok(monkeypatch)
    monkeypatch.setattr(
        "what.controller.routes_stream.list_desktop_devices",
        lambda _backend: [
            "0: what-desktop",
            "1: BlackHole 2ch",
        ],
    )

    app = create_controller_app(cfg, state)
    client = TestClient(app)

    resp = client.post(
        "/control/stream/start",
        json={
            "input_mode": "desktop",
            "mic_enabled": False,
            "desktop_enabled": True,
            "desktop_backend": "avfoundation",
            "desktop_device": ":0",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["stream_desktop_enabled"] is True
    assert body["stream_desktop_output_target"] == "what-desktop"
    assert body["stream_desktop_capture_input"] == ":0"
    assert seen["desktop_enabled"] is True
    assert seen["desktop_backend"] == "avfoundation"
    assert seen["desktop_device"] == ":0"


def test_stream_start_rebinds_output_selector_to_capture_candidate(monkeypatch):
    state = ControllerState()
    cfg = _cfg()
    seen = {}

    def fake_start_service(_cfg, _settings, session_id=None):
        _ = session_id
        return DummyProc()

    def fake_start_client(_cfg, settings):
        seen["desktop_enabled"] = bool(settings.desktop_enabled)
        seen["desktop_backend"] = str(settings.desktop_backend or "")
        seen["desktop_device"] = str(settings.desktop_device or "")
        return DummyProc()

    def fake_stop_service(_proc):
        return None

    def fake_stop_client(_proc):
        return None

    def fake_process_running(proc):
        return proc is not None and proc.poll() is None

    monkeypatch.setattr("what.controller.api.start_service", fake_start_service)
    monkeypatch.setattr("what.controller.api.start_client", fake_start_client)
    monkeypatch.setattr("what.controller.api.stop_service", fake_stop_service)
    monkeypatch.setattr("what.controller.api.stop_client", fake_stop_client)
    monkeypatch.setattr("what.controller.api.process_running", fake_process_running)
    monkeypatch.setattr("what.controller.api._wait_for_service_health", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("what.controller.api._start_stream_log_pump", lambda *_args, **_kwargs: None)
    _patch_routing_ok(monkeypatch)
    monkeypatch.setattr(
        "what.controller.routes_stream.list_desktop_devices",
        lambda _backend: [
            "0: BlackHole 2ch",
            "3: what-desktop",
            "5: Built-in Microphone",
        ],
    )

    app = create_controller_app(cfg, state)
    client = TestClient(app)

    resp = client.post(
        "/control/stream/start",
        json={
            "input_mode": "desktop",
            "mic_enabled": False,
            "desktop_enabled": True,
            "desktop_backend": "avfoundation",
            "desktop_device": ":3",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["stream_desktop_enabled"] is True
    assert body["stream_desktop_output_target"] == "what-desktop"
    assert body["stream_desktop_capture_input"] == ":3"
    assert seen["desktop_enabled"] is True
    assert seen["desktop_backend"] == "avfoundation"
    assert seen["desktop_device"] == ":3"


def test_stream_start_prefers_what_desktop_capture_with_what_desktop_output_target(monkeypatch):
    state = ControllerState()
    cfg = _cfg()
    seen = {}

    def fake_start_service(_cfg, _settings, session_id=None):
        _ = session_id
        return DummyProc()

    def fake_start_client(_cfg, settings):
        seen["desktop_device"] = str(settings.desktop_device or "")
        return DummyProc()

    def fake_stop_service(_proc):
        return None

    def fake_stop_client(_proc):
        return None

    def fake_process_running(proc):
        return proc is not None and proc.poll() is None

    monkeypatch.setattr("what.controller.api.start_service", fake_start_service)
    monkeypatch.setattr("what.controller.api.start_client", fake_start_client)
    monkeypatch.setattr("what.controller.api.stop_service", fake_stop_service)
    monkeypatch.setattr("what.controller.api.stop_client", fake_stop_client)
    monkeypatch.setattr("what.controller.api.process_running", fake_process_running)
    monkeypatch.setattr("what.controller.api._wait_for_service_health", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("what.controller.api._start_stream_log_pump", lambda *_args, **_kwargs: None)
    _patch_routing_ok(monkeypatch)
    monkeypatch.setattr(
        "what.controller.routes_stream.list_desktop_devices",
        lambda _backend: [
            "0: what-desktop",
            "1: BlackHole 2ch",
            "2: Built-in Microphone",
        ],
    )

    app = create_controller_app(cfg, state)
    client = TestClient(app)

    resp = client.post(
        "/control/stream/start",
        json={
            "input_mode": "desktop",
            "mic_enabled": False,
            "desktop_enabled": True,
            "desktop_backend": "avfoundation",
            "desktop_device": ":1",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["stream_desktop_device"] == ":0"
    assert body["stream_desktop_candidate_count"] == 2
    assert body["stream_desktop_output_target"] == "what-desktop"
    assert body["stream_desktop_capture_input"] == ":0"
    assert body["stream_desktop_output_resolved"] is True
    assert body["stream_desktop_capture_resolved"] is True
    assert body["stream_desktop_fallback_enabled"] is False
    assert seen["desktop_device"] == ":0"


def test_stream_start_reports_fallback_enabled_when_env_on(monkeypatch):
    state = ControllerState()
    cfg = _cfg()

    def fake_start_service(_cfg, _settings, session_id=None):
        _ = session_id
        return DummyProc()

    def fake_start_client(_cfg, _settings):
        return DummyProc()

    def fake_stop_service(_proc):
        return None

    def fake_stop_client(_proc):
        return None

    def fake_process_running(proc):
        return proc is not None and proc.poll() is None

    monkeypatch.setenv("WHAT_DESKTOP_CAPTURE_FALLBACK_ENABLE", "1")
    monkeypatch.setattr("what.controller.api.start_service", fake_start_service)
    monkeypatch.setattr("what.controller.api.start_client", fake_start_client)
    monkeypatch.setattr("what.controller.api.stop_service", fake_stop_service)
    monkeypatch.setattr("what.controller.api.stop_client", fake_stop_client)
    monkeypatch.setattr("what.controller.api.process_running", fake_process_running)
    monkeypatch.setattr("what.controller.api._wait_for_service_health", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("what.controller.api._start_stream_log_pump", lambda *_args, **_kwargs: None)
    _patch_routing_ok(monkeypatch)
    monkeypatch.setattr(
        "what.controller.routes_stream.list_desktop_devices",
        lambda _backend: [
            "0: what-desktop",
            "1: BlackHole 2ch",
            "2: Loopback Audio",
        ],
    )

    app = create_controller_app(cfg, state)
    client = TestClient(app)

    resp = client.post(
        "/control/stream/start",
        json={
            "input_mode": "desktop",
            "mic_enabled": False,
            "desktop_enabled": True,
            "desktop_backend": "avfoundation",
            "desktop_device": ":1",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["stream_desktop_fallback_enabled"] is True


def test_stream_start_disables_desktop_when_output_route_unresolved(monkeypatch):
    state = ControllerState()
    cfg = _cfg()
    seen = {}

    def fake_start_service(_cfg, _settings, session_id=None):
        _ = session_id
        return DummyProc()

    def fake_start_client(_cfg, settings):
        seen["desktop_enabled"] = bool(settings.desktop_enabled)
        return DummyProc()

    def fake_stop_service(_proc):
        return None

    def fake_stop_client(_proc):
        return None

    def fake_process_running(proc):
        return proc is not None and proc.poll() is None

    monkeypatch.setattr("what.controller.api.start_service", fake_start_service)
    monkeypatch.setattr("what.controller.api.start_client", fake_start_client)
    monkeypatch.setattr("what.controller.api.stop_service", fake_stop_service)
    monkeypatch.setattr("what.controller.api.stop_client", fake_stop_client)
    monkeypatch.setattr("what.controller.api.process_running", fake_process_running)
    monkeypatch.setattr("what.controller.api._wait_for_service_health", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("what.controller.api._start_stream_log_pump", lambda *_args, **_kwargs: None)
    _patch_routing_unresolved(monkeypatch)
    monkeypatch.setattr(
        "what.controller.routes_stream.list_desktop_devices",
        lambda _backend: [
            "0: what-desktop",
            "1: BlackHole 2ch",
        ],
    )

    app = create_controller_app(cfg, state)
    client = TestClient(app)

    resp = client.post(
        "/control/stream/start",
        json={
            "input_mode": "desktop",
            "mic_enabled": False,
            "desktop_enabled": True,
            "desktop_backend": "avfoundation",
            "desktop_device": ":1",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["stream_desktop_enabled"] is False
    assert body["stream_desktop_capture_input"] == ""
    assert body["stream_desktop_device"] == ""
    assert body["stream_desktop_disabled_reason"] == "no_desktop_output_route"
    assert body["stream_desktop_output_error"] == "no_desktop_output_route"
    assert seen["desktop_enabled"] is False


def test_stream_settings_legacy_desktop_device_does_not_override_capture_authority(monkeypatch, tmp_path):
    state = ControllerState()
    cfg = _cfg()
    cfg.settings_path = str(tmp_path / "controller_settings.json")
    state.stream_settings.input_mode = "desktop"
    state.stream_settings.desktop_enabled = True
    state.stream_settings.desktop_backend = "avfoundation"
    state.stream_settings.desktop_output_target = "what-desktop"
    state.stream_settings.desktop_capture_input = ":1"
    state.stream_settings.desktop_device = ":1"

    monkeypatch.setattr("what.controller.api._wait_for_service_health", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("what.controller.api._start_stream_log_pump", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "what.controller.routes_stream.list_desktop_devices",
        lambda _backend: ["0: what-desktop", "1: BlackHole 2ch", "3: BlackHole 16ch"],
    )

    app = create_controller_app(cfg, state)
    client = TestClient(app)
    resp = client.post(
        "/control/stream/settings",
        json={
            "desktop_device": ":3",
            "desktop_enabled": True,
            "desktop_backend": "avfoundation",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["stream_desktop_capture_input"] == ":0"
    assert body["stream_desktop_output_target"] == "what-desktop"


def test_control_status_desktop_alias_mirrors_capture_input_authority(monkeypatch, tmp_path):
    state = ControllerState()
    cfg = _cfg()
    cfg.settings_path = str(tmp_path / "controller_settings.json")
    state.stream_settings.desktop_enabled = True
    state.stream_settings.desktop_backend = "avfoundation"
    state.stream_settings.desktop_capture_input = ":4"
    state.stream_settings.desktop_device = ":1"

    monkeypatch.setattr("what.controller.api._wait_for_service_health", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("what.controller.api._start_stream_log_pump", lambda *_args, **_kwargs: None)

    app = create_controller_app(cfg, state)
    client = TestClient(app)
    status = client.get("/control/status")
    assert status.status_code == 200
    body = status.json()
    assert body["stream_desktop_capture_input"] == ":4"
    assert body["stream_desktop_device"] == ":4"


def test_stream_start_fallback_probe_keeps_current_capture_input_when_signal_present(monkeypatch, tmp_path):
    state = ControllerState()
    cfg = _cfg()
    cfg.settings_path = str(tmp_path / "controller_settings.json")
    started: list[str] = []

    def fake_start_service(_cfg, _settings, session_id=None):
        _ = session_id
        return DummyProc()

    def fake_start_client(_cfg, settings):
        started.append(str(settings.desktop_capture_input or settings.desktop_device or ""))
        return DummyProc()

    def fake_stop_service(_proc):
        return None

    def fake_stop_client(_proc):
        return None

    def fake_process_running(proc):
        return proc is not None and proc.poll() is None

    monkeypatch.setenv("WHAT_DESKTOP_CAPTURE_FALLBACK_ENABLE", "1")
    monkeypatch.setattr("what.controller.api.start_service", fake_start_service)
    monkeypatch.setattr("what.controller.api.start_client", fake_start_client)
    monkeypatch.setattr("what.controller.api.stop_service", fake_stop_service)
    monkeypatch.setattr("what.controller.api.stop_client", fake_stop_client)
    monkeypatch.setattr("what.controller.api.process_running", fake_process_running)
    monkeypatch.setattr("what.controller.api._wait_for_service_health", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("what.controller.api._start_stream_log_pump", lambda *_args, **_kwargs: None)
    _patch_routing_ok(monkeypatch)
    monkeypatch.setattr(
        "what.controller.routes_stream.list_desktop_devices",
        lambda _backend: [
            "0: what-desktop",
            "1: BlackHole 2ch",
            "2: Loopback Audio",
        ],
    )
    probe_states = iter(["silent", "signal"])
    monkeypatch.setattr(
        "what.controller.routes_stream._wait_for_desktop_probe_state",
        lambda *_args, **_kwargs: next(probe_states),
    )
    monkeypatch.setattr(
        "what.controller.routes_stream._scan_candidate_levels",
        lambda _backend, selectors: [
            (selectors[0], "signal", 8),
            (selectors[1], "silent", 0),
        ],
    )
    monkeypatch.setattr(
        "what.controller.routes_stream._latest_desktop_probe_detail",
        lambda *_args, **_kwargs: (0, 1024),
    )

    app = create_controller_app(cfg, state)
    client = TestClient(app)
    resp = client.post(
        "/control/stream/start",
        json={
            "input_mode": "desktop",
            "desktop_enabled": True,
            "desktop_backend": "avfoundation",
            "desktop_output_target": "what-desktop",
            "desktop_capture_input": ":1",
            "mic_enabled": False,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["stream_desktop_capture_input"] == ":0"
    assert body["stream_desktop_device"] == ":0"
    assert started == [":0"]


def test_stream_start_single_candidate_retry_keeps_capture_input_authority(monkeypatch, tmp_path):
    state = ControllerState()
    cfg = _cfg()
    cfg.settings_path = str(tmp_path / "controller_settings.json")
    started: list[str] = []

    def fake_start_service(_cfg, _settings, session_id=None):
        _ = session_id
        return DummyProc()

    def fake_start_client(_cfg, settings):
        started.append(str(settings.desktop_capture_input or settings.desktop_device or ""))
        return DummyProc()

    def fake_stop_service(_proc):
        return None

    def fake_stop_client(_proc):
        return None

    def fake_process_running(proc):
        return proc is not None and proc.poll() is None

    monkeypatch.setattr("what.controller.api.start_service", fake_start_service)
    monkeypatch.setattr("what.controller.api.start_client", fake_start_client)
    monkeypatch.setattr("what.controller.api.stop_service", fake_stop_service)
    monkeypatch.setattr("what.controller.api.stop_client", fake_stop_client)
    monkeypatch.setattr("what.controller.api.process_running", fake_process_running)
    monkeypatch.setattr("what.controller.api._wait_for_service_health", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("what.controller.api._start_stream_log_pump", lambda *_args, **_kwargs: None)
    _patch_routing_ok(monkeypatch)
    monkeypatch.setattr(
        "what.controller.routes_stream.list_desktop_devices",
        lambda _backend: [
            "0: what-desktop",
        ],
    )
    probe_states = iter(["error", "signal"])
    monkeypatch.setattr(
        "what.controller.routes_stream._wait_for_desktop_probe_state",
        lambda *_args, **_kwargs: next(probe_states),
    )

    app = create_controller_app(cfg, state)
    client = TestClient(app)
    resp = client.post(
        "/control/stream/start",
        json={
            "input_mode": "desktop",
            "desktop_enabled": True,
            "desktop_backend": "avfoundation",
            "desktop_output_target": "what-desktop",
            "desktop_capture_input": ":1",
            "mic_enabled": False,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["stream_desktop_capture_input"] == ":0"
    assert body["stream_desktop_device"] == ":0"
    assert started == [":0", ":0"]
    lines = [line for _, line in state.stream_logs]
    assert any("desktop capture startup retry:" in line for line in lines)


def test_stream_start_single_candidate_true_zero_retries_and_keeps_capture_authority(monkeypatch, tmp_path):
    state = ControllerState()
    cfg = _cfg()
    cfg.settings_path = str(tmp_path / "controller_settings.json")
    started: list[str] = []

    def fake_start_service(_cfg, _settings, session_id=None):
        _ = session_id
        return DummyProc()

    def fake_start_client(_cfg, settings):
        started.append(str(settings.desktop_capture_input or settings.desktop_device or ""))
        return DummyProc()

    monkeypatch.setattr("what.controller.api.start_service", fake_start_service)
    monkeypatch.setattr("what.controller.api.start_client", fake_start_client)
    monkeypatch.setattr("what.controller.api.stop_service", lambda _p: None)
    monkeypatch.setattr("what.controller.api.stop_client", lambda _p: None)
    monkeypatch.setattr("what.controller.api.process_running", lambda p: p is not None and p.poll() is None)
    monkeypatch.setattr("what.controller.api._wait_for_service_health", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("what.controller.api._start_stream_log_pump", lambda *_args, **_kwargs: None)
    _patch_routing_ok(monkeypatch)
    monkeypatch.setattr(
        "what.controller.routes_stream.list_desktop_devices",
        lambda _backend: [
            "0: what-desktop",
        ],
    )
    probe_states = iter(["silent", "signal"])
    monkeypatch.setattr(
        "what.controller.routes_stream._wait_for_desktop_probe_state",
        lambda *_args, **_kwargs: next(probe_states),
    )
    monkeypatch.setattr(
        "what.controller.routes_stream._latest_desktop_probe_detail",
        lambda *_args, **_kwargs: (0, 2048),
    )

    app = create_controller_app(cfg, state)
    client = TestClient(app)
    resp = client.post(
        "/control/stream/start",
        json={
            "input_mode": "desktop",
            "desktop_enabled": True,
            "desktop_backend": "avfoundation",
            "desktop_output_target": "what-desktop",
            "desktop_capture_input": ":1",
            "mic_enabled": False,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["stream_desktop_capture_input"] == ":0"
    assert body["stream_desktop_device"] == ":0"
    assert started == [":0", ":0"]
    lines = [line for _, line in state.stream_logs]
    assert any("desktop capture startup true-zero detected" in line for line in lines)


def test_stream_start_with_fallback_disabled_keeps_initial_capture_candidate(monkeypatch, tmp_path):
    state = ControllerState()
    cfg = _cfg()
    cfg.settings_path = str(tmp_path / "controller_settings.json")
    started: list[str] = []

    def fake_start_service(_cfg, _settings, session_id=None):
        _ = session_id
        return DummyProc()

    def fake_start_client(_cfg, settings):
        started.append(str(settings.desktop_capture_input or settings.desktop_device or ""))
        return DummyProc()

    def fake_stop_service(_proc):
        return None

    def fake_stop_client(_proc):
        return None

    def fake_process_running(proc):
        return proc is not None and proc.poll() is None

    monkeypatch.delenv("WHAT_DESKTOP_CAPTURE_FALLBACK_ENABLE", raising=False)
    monkeypatch.setattr("what.controller.api.start_service", fake_start_service)
    monkeypatch.setattr("what.controller.api.start_client", fake_start_client)
    monkeypatch.setattr("what.controller.api.stop_service", fake_stop_service)
    monkeypatch.setattr("what.controller.api.stop_client", fake_stop_client)
    monkeypatch.setattr("what.controller.api.process_running", fake_process_running)
    monkeypatch.setattr("what.controller.api._wait_for_service_health", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("what.controller.api._start_stream_log_pump", lambda *_args, **_kwargs: None)
    _patch_routing_ok(monkeypatch)
    monkeypatch.setattr(
        "what.controller.routes_stream.list_desktop_devices",
        lambda _backend: [
            "0: what-desktop",
            "1: BlackHole 2ch",
            "2: Loopback Audio",
        ],
    )

    app = create_controller_app(cfg, state)
    client = TestClient(app)
    resp = client.post(
        "/control/stream/start",
        json={
            "input_mode": "desktop",
            "desktop_enabled": True,
            "desktop_backend": "avfoundation",
            "desktop_output_target": "what-desktop",
            "desktop_capture_input": ":1",
            "mic_enabled": False,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["stream_desktop_fallback_enabled"] is False
    assert body["stream_desktop_fallback_to"] == ""
    assert body["stream_desktop_capture_input"] == ":0"
    assert body["stream_desktop_device"] == ":0"
    assert started == [":0"]


def test_stream_start_native_backend_starts_helper(monkeypatch, tmp_path):
    state = ControllerState()
    cfg = _cfg()
    cfg.settings_path = str(tmp_path / "controller_settings.json")

    def fake_start_service(_cfg, _settings, session_id=None):
        _ = session_id
        return DummyProc()

    def fake_start_client(_cfg, _settings):
        return DummyProc()

    monkeypatch.setenv("WHAT_DESKTOP_SOURCE_BACKEND", "native_helper")
    monkeypatch.setattr("what.controller.api.start_service", fake_start_service)
    monkeypatch.setattr("what.controller.api.start_client", fake_start_client)
    monkeypatch.setattr("what.controller.api.stop_service", lambda _p: None)
    monkeypatch.setattr("what.controller.api.stop_client", lambda _p: None)
    monkeypatch.setattr("what.controller.api.process_running", lambda p: p is not None and p.poll() is None)
    monkeypatch.setattr("what.controller.api._wait_for_service_health", lambda *_a, **_k: None)
    monkeypatch.setattr("what.controller.api._start_stream_log_pump", lambda *_a, **_k: None)
    _patch_routing_ok(monkeypatch)
    monkeypatch.setattr(
        "what.controller.routes_stream.list_desktop_devices",
        lambda _backend: ["2: what-desktop", "0: BlackHole 2ch"],
    )
    seen_start = {}
    def fake_helper_start(**kwargs):
        seen_start.update(kwargs)
        return {"ok": True, "changed": True, "status": {"running": True}}
    monkeypatch.setattr(
        "what.controller.routes_stream.native_desktop_helper_manager.start",
        fake_helper_start,
    )
    monkeypatch.setattr(
        "what.controller.routes_stream.native_desktop_helper_manager.get_status",
        lambda **_kwargs: {
            "running": True,
            "health_payload": {
                "capture_state": "signal",
                "chunks_sent": 2,
            },
        },
    )
    monkeypatch.setattr(
        "what.controller.routes_stream._emit_desktop_start_ping",
        lambda: {"ok": True, "pid": 1234, "sound": "/System/Library/Sounds/Ping.aiff"},
    )
    monkeypatch.setattr(
        "what.controller.routes_stream._wait_for_desktop_probe_state",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("legacy probe path should not run")),
    )

    app = create_controller_app(cfg, state)
    client = TestClient(app)
    resp = client.post(
        "/control/stream/start",
        json={
            "input_mode": "desktop",
            "desktop_enabled": True,
            "desktop_backend": "avfoundation",
            "mic_enabled": False,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["stream_desktop_native_backend"] == "native_helper"
    assert body["stream_desktop_native_helper"]["ok"] is True
    assert seen_start["capture_mode"] == "native-capture"


def test_stream_start_native_backend_prefers_loopback_selector_for_what_desktop(monkeypatch, tmp_path):
    state = ControllerState()
    cfg = _cfg()
    cfg.settings_path = str(tmp_path / "controller_settings.json")
    starts: list[str] = []
    current = {"sel": ""}

    def fake_start_service(_cfg, _settings, session_id=None):
        _ = session_id
        return DummyProc()

    def fake_start_client(_cfg, _settings):
        return DummyProc()

    def fake_helper_start(**kwargs):
        sel = str(kwargs.get("desktop_device") or "")
        current["sel"] = sel
        starts.append(sel)
        return {"ok": True, "changed": True, "status": {"running": True, "args": kwargs}}

    def fake_helper_status(**_kwargs):
        if current["sel"] == ":0":
            return {"running": True, "health_payload": {"capture_state": "signal", "chunks_sent": 3}}
        return {"running": True, "health_payload": {"capture_state": "silent", "chunks_sent": 1}}

    monkeypatch.setenv("WHAT_DESKTOP_SOURCE_BACKEND", "native_helper")
    monkeypatch.setattr("what.controller.api.start_service", fake_start_service)
    monkeypatch.setattr("what.controller.api.start_client", fake_start_client)
    monkeypatch.setattr("what.controller.api.stop_service", lambda _p: None)
    monkeypatch.setattr("what.controller.api.stop_client", lambda _p: None)
    monkeypatch.setattr("what.controller.api.process_running", lambda p: p is not None and p.poll() is None)
    monkeypatch.setattr("what.controller.api._wait_for_service_health", lambda *_a, **_k: None)
    monkeypatch.setattr("what.controller.api._start_stream_log_pump", lambda *_a, **_k: None)
    monkeypatch.setattr("what.controller.routes_stream._emit_desktop_start_ping", lambda: {"ok": True})
    _patch_routing_ok(monkeypatch)
    monkeypatch.setattr(
        "what.controller.routes_stream.list_desktop_devices",
        lambda _backend: ["2: what-desktop", "0: BlackHole 2ch"],
    )
    monkeypatch.setattr("what.controller.routes_stream.native_desktop_helper_manager.start", fake_helper_start)
    monkeypatch.setattr("what.controller.routes_stream.native_desktop_helper_manager.get_status", fake_helper_status)
    monkeypatch.setattr("what.controller.routes_stream.native_desktop_helper_manager.stop", lambda **_k: {"ok": True})

    app = create_controller_app(cfg, state)
    client = TestClient(app)
    resp = client.post(
        "/control/stream/start",
        json={
            "input_mode": "desktop",
            "desktop_enabled": True,
            "desktop_backend": "avfoundation",
            "mic_enabled": False,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert starts == [":0"]
    assert body["stream_desktop_native_capture_selector"] == ":0"


def test_stream_stop_native_backend_stops_helper(monkeypatch, tmp_path):
    state = ControllerState()
    cfg = _cfg()
    cfg.settings_path = str(tmp_path / "controller_settings.json")
    monkeypatch.setenv("WHAT_DESKTOP_SOURCE_BACKEND", "native_helper")
    monkeypatch.setattr("what.controller.api.stop_client", lambda _p: None)
    monkeypatch.setattr(
        "what.controller.routes_stream.native_desktop_helper_manager.stop",
        lambda **kwargs: {"ok": True, "changed": True, "status": {"running": False, "args": kwargs}},
    )
    monkeypatch.setattr(
        "what.controller.api.desktop_audio_manager.uninstall",
        lambda _root, _receipt: {"ok": True, "changed": False},
    )

    app = create_controller_app(cfg, state)
    client = TestClient(app)
    resp = client.post("/control/stream/stop", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["stream_desktop_native_backend"] == "native_helper"
    assert body["stream_desktop_native_helper_stop"]["ok"] is True


def test_stream_start_reselects_capture_input_after_index_drift_from_persisted_settings(monkeypatch, tmp_path):
    cfg = _cfg()
    cfg.settings_path = str(tmp_path / "controller_settings.json")

    # Session 1: persist a capture selector that will disappear after drift.
    state1 = ControllerState()
    app1 = create_controller_app(cfg, state1)
    client1 = TestClient(app1)
    resp1 = client1.post(
        "/control/stream/settings",
        json={
            "input_mode": "desktop",
            "desktop_enabled": True,
            "desktop_backend": "avfoundation",
            "desktop_output_target": "what-desktop",
            "desktop_capture_input": ":1",
            "mic_enabled": False,
        },
    )
    assert resp1.status_code == 200

    # Session 2: selector indices drift; old :1 no longer exists.
    state2 = ControllerState()
    seen = {}

    def fake_start_service(_cfg, _settings, session_id=None):
        _ = session_id
        return DummyProc()

    def fake_start_client(_cfg, settings):
        seen["capture"] = str(settings.desktop_capture_input or settings.desktop_device or "")
        return DummyProc()

    monkeypatch.setattr("what.controller.api.start_service", fake_start_service)
    monkeypatch.setattr("what.controller.api.start_client", fake_start_client)
    monkeypatch.setattr("what.controller.api.stop_service", lambda _p: None)
    monkeypatch.setattr("what.controller.api.stop_client", lambda _p: None)
    monkeypatch.setattr("what.controller.api.process_running", lambda p: p is not None and p.poll() is None)
    monkeypatch.setattr("what.controller.api._wait_for_service_health", lambda *_a, **_k: None)
    monkeypatch.setattr("what.controller.api._start_stream_log_pump", lambda *_a, **_k: None)
    _patch_routing_ok(monkeypatch)
    monkeypatch.setattr(
        "what.controller.routes_stream.list_desktop_devices",
        lambda _backend: [
            "4: what-desktop",
            "7: BlackHole 2ch",
            "9: Built-in Microphone",
        ],
    )

    app2 = create_controller_app(cfg, state2)
    client2 = TestClient(app2)
    resp2 = client2.post("/control/stream/start", json={"desktop_enabled": True, "mic_enabled": False})
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["ok"] is True
    assert body2["stream_desktop_output_target"] == "what-desktop"
    assert body2["stream_desktop_capture_input"] == ":4"
    assert body2["stream_desktop_device"] == ":4"
    assert seen["capture"] == ":4"


def test_stream_start_reselects_output_target_after_label_drift_from_persisted_settings(monkeypatch, tmp_path):
    cfg = _cfg()
    cfg.settings_path = str(tmp_path / "controller_settings.json")

    # Session 1: persist an obsolete output target label.
    state1 = ControllerState()
    app1 = create_controller_app(cfg, state1)
    client1 = TestClient(app1)
    resp1 = client1.post(
        "/control/stream/settings",
        json={
            "input_mode": "desktop",
            "desktop_enabled": True,
            "desktop_backend": "avfoundation",
            "desktop_output_target": "what-desktop-old",
            "desktop_capture_input": ":1",
            "mic_enabled": False,
        },
    )
    assert resp1.status_code == 200

    # Session 2: runtime inventory has canonical what-desktop target.
    state2 = ControllerState()
    seen = {}

    def fake_start_service(_cfg, _settings, session_id=None):
        _ = session_id
        return DummyProc()

    def fake_start_client(_cfg, settings):
        seen["output_target"] = str(settings.desktop_output_target or "")
        seen["capture"] = str(settings.desktop_capture_input or settings.desktop_device or "")
        return DummyProc()

    monkeypatch.setattr("what.controller.api.start_service", fake_start_service)
    monkeypatch.setattr("what.controller.api.start_client", fake_start_client)
    monkeypatch.setattr("what.controller.api.stop_service", lambda _p: None)
    monkeypatch.setattr("what.controller.api.stop_client", lambda _p: None)
    monkeypatch.setattr("what.controller.api.process_running", lambda p: p is not None and p.poll() is None)
    monkeypatch.setattr("what.controller.api._wait_for_service_health", lambda *_a, **_k: None)
    monkeypatch.setattr("what.controller.api._start_stream_log_pump", lambda *_a, **_k: None)
    _patch_routing_ok(monkeypatch)
    monkeypatch.setattr(
        "what.controller.routes_stream.list_desktop_devices",
        lambda _backend: [
            "0: what-desktop",
            "2: BlackHole 2ch",
            "6: Built-in Microphone",
        ],
    )

    app2 = create_controller_app(cfg, state2)
    client2 = TestClient(app2)
    resp2 = client2.post("/control/stream/start", json={"desktop_enabled": True, "mic_enabled": False})
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["ok"] is True
    assert body2["stream_desktop_output_target"] == "what-desktop"
    assert body2["stream_desktop_capture_input"] == ":0"
    assert seen["output_target"] == "what-desktop"
    assert seen["capture"] == ":0"


def test_stream_start_reselects_mic_device_after_selector_drift(monkeypatch, tmp_path):
    cfg = _cfg()
    cfg.settings_path = str(tmp_path / "controller_settings.json")

    # Session 1: persist a mic selector that will disappear after restart.
    state1 = ControllerState()
    app1 = create_controller_app(cfg, state1)
    client1 = TestClient(app1)
    resp1 = client1.post(
        "/control/stream/settings",
        json={
            "input_mode": "mic",
            "mic_enabled": True,
            "mic_backend": "avfoundation",
            "mic_device": ":9",
            "desktop_enabled": False,
        },
    )
    assert resp1.status_code == 200

    # Session 2: :9 is gone; controller should pick an available mic selector.
    state2 = ControllerState()
    seen = {}

    def fake_start_service(_cfg, _settings, session_id=None):
        _ = session_id
        return DummyProc()

    def fake_start_client(_cfg, settings):
        seen["mic_device"] = str(settings.mic_device or "")
        return DummyProc()

    monkeypatch.setattr("what.controller.api.start_service", fake_start_service)
    monkeypatch.setattr("what.controller.api.start_client", fake_start_client)
    monkeypatch.setattr("what.controller.api.stop_service", lambda _p: None)
    monkeypatch.setattr("what.controller.api.stop_client", lambda _p: None)
    monkeypatch.setattr("what.controller.api.process_running", lambda p: p is not None and p.poll() is None)
    monkeypatch.setattr("what.controller.api._wait_for_service_health", lambda *_a, **_k: None)
    monkeypatch.setattr("what.controller.api._start_stream_log_pump", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "what.controller.routes_stream.list_desktop_devices",
        lambda _backend: [
            "0: MacBook Pro Speakers",
            "1: MacBook Pro Microphone",
            "3: what-desktop",
            "5: BlackHole 2ch",
        ],
    )

    app2 = create_controller_app(cfg, state2)
    client2 = TestClient(app2)
    resp2 = client2.post("/control/stream/start", json={"mic_enabled": True, "desktop_enabled": False})
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["ok"] is True
    assert seen["mic_device"] == ":1"


def test_stream_start_reselects_mic_when_persisted_selector_is_output_device(monkeypatch, tmp_path):
    cfg = _cfg()
    cfg.settings_path = str(tmp_path / "controller_settings.json")

    state1 = ControllerState()
    app1 = create_controller_app(cfg, state1)
    client1 = TestClient(app1)
    resp1 = client1.post(
        "/control/stream/settings",
        json={
            "input_mode": "mic",
            "mic_enabled": True,
            "mic_backend": "avfoundation",
            "mic_device": ":0",
            "desktop_enabled": False,
        },
    )
    assert resp1.status_code == 200

    state2 = ControllerState()
    seen = {}

    def fake_start_service(_cfg, _settings, session_id=None):
        _ = session_id
        return DummyProc()

    def fake_start_client(_cfg, settings):
        seen["mic_device"] = str(settings.mic_device or "")
        return DummyProc()

    monkeypatch.setattr("what.controller.api.start_service", fake_start_service)
    monkeypatch.setattr("what.controller.api.start_client", fake_start_client)
    monkeypatch.setattr("what.controller.api.stop_service", lambda _p: None)
    monkeypatch.setattr("what.controller.api.stop_client", lambda _p: None)
    monkeypatch.setattr("what.controller.api.process_running", lambda p: p is not None and p.poll() is None)
    monkeypatch.setattr("what.controller.api._wait_for_service_health", lambda *_a, **_k: None)
    monkeypatch.setattr("what.controller.api._start_stream_log_pump", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "what.controller.routes_stream.list_desktop_devices",
        lambda _backend: [
            "0: MacBook Pro Speakers",
            "1: MacBook Pro Microphone",
            "4: what-desktop",
        ],
    )
    monkeypatch.setattr(
        "what.controller.routes_stream._probe_mic_candidate",
        lambda _backend, selector: {"state": "silent", "level": 0} if selector == ":1" else {"state": "error", "level": -1},
    )

    app2 = create_controller_app(cfg, state2)
    client2 = TestClient(app2)
    resp2 = client2.post("/control/stream/start", json={"mic_enabled": True, "desktop_enabled": False})
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["ok"] is True
    assert seen["mic_device"] == ":1"
