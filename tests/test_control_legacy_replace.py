from types import SimpleNamespace

from what.cli.handle_control import handle_control


def _args():
    return SimpleNamespace(
        host="127.0.0.1",
        port=8780,
        service_host="127.0.0.1",
        service_port=8765,
        config=None,
        settings_path=None,
    )


def test_handle_control_reuses_modern_controller(monkeypatch):
    called = {"run": 0, "kill": 0}

    monkeypatch.setattr(
        "what.cli.handle_control._controller_status",
        lambda *_args, **_kwargs: {"running": False, "stream_running": False},
    )
    monkeypatch.setattr("what.cli.handle_control._kill_listener_on_port", lambda _p: called.__setitem__("kill", 1))
    monkeypatch.setattr("what.cli.handle_control.run_controller", lambda _cfg: called.__setitem__("run", 1))

    handle_control(_args())
    assert called["run"] == 0
    assert called["kill"] == 0


def test_handle_control_replaces_legacy_controller(monkeypatch):
    called = {"run": 0, "kill": 0}

    monkeypatch.setattr(
        "what.cli.handle_control._controller_status",
        lambda *_args, **_kwargs: {"running": False},
    )
    monkeypatch.setattr("what.cli.handle_control._kill_listener_on_port", lambda _p: called.__setitem__("kill", 1))
    monkeypatch.setattr("what.cli.handle_control.run_controller", lambda _cfg: called.__setitem__("run", 1))

    handle_control(_args())
    assert called["run"] == 1
    assert called["kill"] == 1


def test_handle_control_starts_when_no_controller(monkeypatch):
    called = {"run": 0}
    monkeypatch.setattr("what.cli.handle_control._controller_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("what.cli.handle_control.run_controller", lambda _cfg: called.__setitem__("run", 1))
    handle_control(_args())
    assert called["run"] == 1
