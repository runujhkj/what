from fastapi.testclient import TestClient

from what.controller.api import create_controller_app
from what.controller.state import ControllerState
from what.controller.types import ControllerConfig


def _cfg(tmp_path) -> ControllerConfig:
    return ControllerConfig(
        host="127.0.0.1",
        port=8780,
        service_host="127.0.0.1",
        service_port=8765,
        config_path=None,
        settings_path=str(tmp_path / "controller_settings.json"),
    )


def test_status_includes_desktop_audio_manager(monkeypatch, tmp_path):
    cfg = _cfg(tmp_path)
    state = ControllerState()
    monkeypatch.setattr(
        "what.controller.api.desktop_audio_manager.get_status",
        lambda _root, _receipt, **_kwargs: {
            "supported": True,
            "installed": True,
            "managed_install": True,
            "installed_drivers": ["BlackHole2ch.driver"],
        },
    )
    app = create_controller_app(cfg, state)
    client = TestClient(app)

    resp = client.get("/control/status")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["desktop_audio_manager"]["supported"] is True
    assert payload["desktop_audio_manager"]["installed"] is True
    assert payload["desktop_audio_manager"]["managed_install"] is True


def test_desktop_audio_status_endpoint(monkeypatch, tmp_path):
    cfg = _cfg(tmp_path)
    state = ControllerState()
    monkeypatch.setattr(
        "what.controller.api.desktop_audio_manager.get_status",
        lambda _root, _receipt, **_kwargs: {
            "supported": True,
            "installed": False,
            "managed_install": False,
        },
    )
    app = create_controller_app(cfg, state)
    client = TestClient(app)

    resp = client.get("/control/desktop-audio/status")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["status"]["installed"] is False


def test_desktop_audio_install_success_logs(monkeypatch, tmp_path):
    cfg = _cfg(tmp_path)
    state = ControllerState()
    monkeypatch.setattr(
        "what.controller.api.desktop_audio_manager.install",
        lambda _root, _receipt, configure_routing=True: {
            "ok": True,
            "changed": True,
            "configure_routing": bool(configure_routing),
            "status": {"installed": True},
        },
    )
    app = create_controller_app(cfg, state)
    client = TestClient(app)

    resp = client.post("/control/desktop-audio/install")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    lines = [line for _, line in state.stream_logs if line.startswith("ui: ")]
    assert any("desktop manager api: install complete" in line for line in lines)


def test_desktop_audio_install_failure_logs(monkeypatch, tmp_path):
    cfg = _cfg(tmp_path)
    state = ControllerState()
    monkeypatch.setattr(
        "what.controller.api.desktop_audio_manager.install",
        lambda _root, _receipt, configure_routing=True: {
            "ok": False,
            "error": "missing_pkg",
            "configure_routing": bool(configure_routing),
            "status": {"installed": False},
        },
    )
    app = create_controller_app(cfg, state)
    client = TestClient(app)

    resp = client.post("/control/desktop-audio/install")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is False
    assert payload["error"] == "missing_pkg"
    lines = [line for _, line in state.stream_logs if line.startswith("ui: ")]
    assert any("desktop manager api: install failed (missing_pkg)" in line for line in lines)


def test_desktop_audio_install_driver_only_mode(monkeypatch, tmp_path):
    cfg = _cfg(tmp_path)
    state = ControllerState()
    seen = {"configure_routing": None}

    def fake_install(_root, _receipt, configure_routing=True):
        seen["configure_routing"] = bool(configure_routing)
        return {"ok": True, "changed": True, "routing_ok": True, "status": {"installed": True}}

    monkeypatch.setattr("what.controller.api.desktop_audio_manager.install", fake_install)
    app = create_controller_app(cfg, state)
    client = TestClient(app)

    resp = client.post("/control/desktop-audio/install", json={"mode": "driver_only"})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert seen["configure_routing"] is False
    lines = [line for _, line in state.stream_logs if line.startswith("ui: ")]
    assert any("desktop manager api: install complete (driver-only)" in line for line in lines)


def test_desktop_audio_install_partial_logs_next_steps(monkeypatch, tmp_path):
    cfg = _cfg(tmp_path)
    state = ControllerState()
    monkeypatch.setattr(
        "what.controller.api.desktop_audio_manager.install",
        lambda _root, _receipt, configure_routing=True: {
            "ok": True,
            "changed": True,
            "configure_routing": bool(configure_routing),
            "routing_ok": False,
            "routing_error": "missing_target_output",
            "routing_detail": {"detail": "no routable target output found"},
            "manual_steps": [
                "Create a Multi-Output Device named 'what-desktop'.",
                "Include your listening output and BlackHole.",
            ],
            "status": {"installed": True},
        },
    )
    app = create_controller_app(cfg, state)
    client = TestClient(app)

    resp = client.post("/control/desktop-audio/install")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    lines = [line for _, line in state.stream_logs if line.startswith("ui: ")]
    assert any("install partial (routing not ready: missing_target_output)" in line for line in lines)
    assert any("next-step: Create a Multi-Output Device named 'what-desktop'." in line for line in lines)


def test_desktop_audio_uninstall_success_logs(monkeypatch, tmp_path):
    cfg = _cfg(tmp_path)
    state = ControllerState()
    monkeypatch.setattr(
        "what.controller.api.desktop_audio_manager.uninstall",
        lambda _root, _receipt: {"ok": True, "changed": True, "status": {"installed": False}},
    )
    app = create_controller_app(cfg, state)
    client = TestClient(app)

    resp = client.post("/control/desktop-audio/uninstall")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    lines = [line for _, line in state.stream_logs if line.startswith("ui: ")]
    assert any("desktop manager api: uninstall complete" in line for line in lines)


def test_desktop_audio_uninstall_failure_logs(monkeypatch, tmp_path):
    cfg = _cfg(tmp_path)
    state = ControllerState()
    monkeypatch.setattr(
        "what.controller.api.desktop_audio_manager.uninstall",
        lambda _root, _receipt: {"ok": False, "error": "unmanaged_install", "status": {"installed": True}},
    )
    app = create_controller_app(cfg, state)
    client = TestClient(app)

    resp = client.post("/control/desktop-audio/uninstall")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is False
    assert payload["error"] == "unmanaged_install"
    lines = [line for _, line in state.stream_logs if line.startswith("ui: ")]
    assert any("desktop manager api: uninstall failed (unmanaged_install)" in line for line in lines)


def test_desktop_audio_install_failure_log_order_and_step_truncation(monkeypatch, tmp_path):
    cfg = _cfg(tmp_path)
    state = ControllerState()
    monkeypatch.setattr(
        "what.controller.api.desktop_audio_manager.install",
        lambda _root, _receipt, configure_routing=True: {
            "ok": False,
            "error": "install_failed",
            "routing_detail": {"detail": "helper timed out"},
            "stderr": "installer stderr",
            "stdout": "installer stdout",
            "code": 222,
            "manual_steps": [
                "step-1",
                "step-2",
                "step-3",
                "step-4",
                "step-5",
                "step-6-should-not-appear",
            ],
            "status": {"installed": False},
        },
    )
    app = create_controller_app(cfg, state)
    client = TestClient(app)

    resp = client.post("/control/desktop-audio/install")
    assert resp.status_code == 200
    assert resp.json()["ok"] is False
    lines = [line for _, line in state.stream_logs if line.startswith("ui: ")]
    assert lines == [
        "ui: desktop manager api: install failed (install_failed)",
        "ui: desktop manager api: routing detail: helper timed out",
        "ui: desktop manager api: install detail: installer stderr",
        "ui: desktop manager api: install code: 222",
        "ui: desktop manager api: next-step: step-1",
        "ui: desktop manager api: next-step: step-2",
        "ui: desktop manager api: next-step: step-3",
        "ui: desktop manager api: next-step: step-4",
        "ui: desktop manager api: next-step: step-5",
    ]


def test_desktop_audio_uninstall_failure_log_order_and_step_truncation(monkeypatch, tmp_path):
    cfg = _cfg(tmp_path)
    state = ControllerState()
    monkeypatch.setattr(
        "what.controller.api.desktop_audio_manager.uninstall",
        lambda _root, _receipt: {
            "ok": False,
            "error": "uninstall_failed",
            "routing_detail": {"stdout": "routing helper says nope"},
            "manual_steps": ["a", "b", "c", "d", "e", "f"],
            "status": {"installed": True},
        },
    )
    app = create_controller_app(cfg, state)
    client = TestClient(app)

    resp = client.post("/control/desktop-audio/uninstall")
    assert resp.status_code == 200
    assert resp.json()["ok"] is False
    lines = [line for _, line in state.stream_logs if line.startswith("ui: ")]
    assert lines == [
        "ui: desktop manager api: uninstall failed (uninstall_failed)",
        "ui: desktop manager api: routing detail: routing helper says nope",
        "ui: desktop manager api: next-step: a",
        "ui: desktop manager api: next-step: b",
        "ui: desktop manager api: next-step: c",
        "ui: desktop manager api: next-step: d",
        "ui: desktop manager api: next-step: e",
    ]


def test_native_desktop_helper_status_endpoint(monkeypatch, tmp_path):
    cfg = _cfg(tmp_path)
    state = ControllerState()
    monkeypatch.setattr(
        "what.controller.routes_desktop_audio.native_desktop_helper_manager.get_status",
        lambda state_dir: {
            "supported": True,
            "helper_ready": True,
            "running": False,
            "health_payload": {},
        },
    )
    app = create_controller_app(cfg, state)
    client = TestClient(app)

    resp = client.get("/control/native-desktop-helper/status")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["status"]["supported"] is True
    assert "desktop_source_backend" in payload


def test_native_desktop_helper_start_stop_endpoints(monkeypatch, tmp_path):
    cfg = _cfg(tmp_path)
    state = ControllerState()
    state.stream_settings.desktop_capture_input = ":2"

    monkeypatch.setattr(
        "what.controller.routes_desktop_audio.native_desktop_helper_manager.start",
        lambda **kwargs: {"ok": True, "changed": True, "status": {"running": True, "kwargs": kwargs}},
    )
    monkeypatch.setattr(
        "what.controller.routes_desktop_audio.native_desktop_helper_manager.stop",
        lambda **kwargs: {"ok": True, "changed": True, "status": {"running": False, "kwargs": kwargs}},
    )

    app = create_controller_app(cfg, state)
    client = TestClient(app)

    start = client.post("/control/native-desktop-helper/start", json={"capture_mode": "tone"})
    assert start.status_code == 200
    assert start.json()["ok"] is True
    stop = client.post("/control/native-desktop-helper/stop")
    assert stop.status_code == 200
    assert stop.json()["ok"] is True

    ui_lines = [line for _, line in state.stream_logs if line.startswith("ui: native desktop helper")]
    assert any("start ok" in line for line in ui_lines)
    assert any("stop ok" in line for line in ui_lines)


def test_native_desktop_helper_start_defaults_to_native_capture_mode(monkeypatch, tmp_path):
    cfg = _cfg(tmp_path)
    state = ControllerState()
    seen = {}

    def fake_start(**kwargs):
        seen.update(kwargs)
        return {"ok": True, "changed": True, "status": {"running": True}}

    monkeypatch.setattr(
        "what.controller.routes_desktop_audio.native_desktop_helper_manager.start",
        fake_start,
    )

    app = create_controller_app(cfg, state)
    client = TestClient(app)
    resp = client.post("/control/native-desktop-helper/start", json={})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert seen["capture_mode"] == "native-capture"
