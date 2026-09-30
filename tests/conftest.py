import pytest


@pytest.fixture(autouse=True)
def _isolate_controller_process_logs(monkeypatch, tmp_path):
    """Keep controller process/session logs out of repo-level logs/ during tests."""

    def _resolve_log_root(_cfg):
        return tmp_path / "logs"

    monkeypatch.setattr("what.controller.api._resolve_log_root", _resolve_log_root, raising=False)


@pytest.fixture(autouse=True)
def _isolate_optional_model_preload(monkeypatch):
    """Controller unit tests must not download models or initialize native GPU runtimes."""
    monkeypatch.setattr("what.controller.routes_cleanup._preload_backend", lambda: None)


@pytest.fixture(autouse=True)
def _isolate_controller_settings(monkeypatch, tmp_path):
    from what.controller import controller_settings_store as store

    original = store.settings_store_path
    monkeypatch.setattr(
        store, "settings_store_path",
        lambda cfg: original(cfg) if cfg.settings_path else str(tmp_path / "controller_settings.json"),
    )


@pytest.fixture(autouse=True)
def _isolate_stream_api_hardware(request, monkeypatch):
    if request.module.__name__ not in {
        "test_controller_stream_api", "test_controller_mixed_capture_api",
    }:
        return
    from what.controller import routes_stream

    # Individual tests override these defaults to exercise error/retry decisions.
    monkeypatch.setattr(routes_stream, "_probe_mic_candidate", lambda *_a: {"state": "signal"})
    monkeypatch.setattr(routes_stream, "_wait_for_desktop_probe_state", lambda *_a, **_kw: "signal")
    monkeypatch.setattr(routes_stream, "_emit_desktop_start_ping", lambda: {"ok": True})
