from fastapi.testclient import TestClient

from what.controller.api import create_controller_app
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


def test_controller_route_composition_contract(monkeypatch, tmp_path):
    cfg = _cfg(tmp_path)
    state = ControllerState()

    class _Gpu:
        available = False
        device = ""
        device_count = 0
        backend = "none"
        reason = "test"

    monkeypatch.setattr("what.controller.api.detect_gpu", lambda: _Gpu())
    monkeypatch.setattr(
        "what.controller.api.desktop_audio_manager.get_status",
        lambda _root, _receipt, **_kwargs: {"supported": True, "installed": False, "managed_install": False},
    )
    app = create_controller_app(cfg, state)
    client = TestClient(app)

    # Registration contract: key route groups are present.
    paths = set(app.openapi()["paths"].keys())
    assert "/control/status" in paths
    assert "/control/gpu" in paths
    assert "/control/stream/start" in paths
    assert "/control/stream/stop" in paths
    assert "/control/stream/logs" in paths
    assert "/control/stream/events" in paths
    assert "/control/desktop-audio/status" in paths
    assert "/control/session/log" in paths

    # Callability contract for composed endpoints.
    assert client.get("/control/status").status_code == 200
    assert client.get("/control/gpu").status_code == 200
    assert client.get("/control/stream/logs").status_code == 200
    assert client.get("/control/stream/events").status_code == 200
    assert client.get("/control/desktop-audio/status").status_code == 200
    assert client.post("/control/session/log", json={"message": "ping"}).status_code == 200
