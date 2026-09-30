import os
from pathlib import Path

from what.controller import native_desktop_helper_manager as ndhm


class DummyProc:
    def __init__(self, pid: int = 4242):
        self.pid = pid


def test_status_reports_unsupported_platform(monkeypatch, tmp_path):
    monkeypatch.setattr(ndhm, "native_helper_supported", lambda: False)
    monkeypatch.setattr(ndhm, "native_helper_ready", lambda: False)
    monkeypatch.setattr(ndhm, "desktop_source_backend", lambda: "native_helper")
    monkeypatch.setattr(ndhm, "native_helper_path", lambda: Path("/tmp/nope"))
    status = ndhm.get_status(tmp_path)
    assert status["supported"] is False
    assert status["helper_ready"] is False
    assert status["running"] is False


def test_start_fails_when_helper_not_ready(monkeypatch, tmp_path):
    monkeypatch.setattr(ndhm, "native_helper_supported", lambda: True)
    monkeypatch.setattr(ndhm, "native_helper_ready", lambda: False)
    monkeypatch.setattr(ndhm, "desktop_source_backend", lambda: "native_helper")
    monkeypatch.setattr(ndhm, "native_helper_path", lambda: Path("/tmp/nope"))
    out = ndhm.start(
        state_dir=tmp_path,
        session_id="abc",
        service_host="127.0.0.1",
        service_port=8765,
    )
    assert out["ok"] is False
    assert out["error"] == "native_helper_not_ready"


def test_start_success_writes_receipt(monkeypatch, tmp_path):
    helper = tmp_path / "what-desktop-helper"
    helper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    os.chmod(helper, 0o755)

    monkeypatch.setattr(ndhm, "native_helper_supported", lambda: True)
    monkeypatch.setattr(ndhm, "native_helper_ready", lambda: True)
    monkeypatch.setattr(ndhm, "desktop_source_backend", lambda: "native_helper")
    monkeypatch.setattr(ndhm, "native_helper_path", lambda: helper)
    monkeypatch.setattr(ndhm.subprocess, "Popen", lambda *args, **kwargs: DummyProc(7777))
    monkeypatch.setattr(ndhm, "_pid_running", lambda pid: pid == 7777)
    monkeypatch.setattr(ndhm, "_health_check", lambda url, timeout_s=0.5: (True, 200, {}))
    monkeypatch.setattr(ndhm, "_pick_health_port", lambda preferred: preferred)

    out = ndhm.start(
        state_dir=tmp_path,
        session_id="s1",
        service_host="127.0.0.1",
        service_port=8765,
        ws_path="/ingest",
        pair_path="/pair",
        capture_mode="tone",
        desktop_device=":2",
        health_port=8793,
    )
    assert out["ok"] is True
    assert out["changed"] is True
    status = out["status"]
    assert status["running"] is True
    assert status["pid"] == 7777


def test_stop_clears_receipt(monkeypatch, tmp_path):
    receipt = tmp_path / ndhm.RECEIPT_FILE
    receipt.write_text('{"pid": 9999, "health_url": "http://127.0.0.1:8793/health"}', encoding="utf-8")
    monkeypatch.setattr(ndhm, "_terminate_pid", lambda pid: pid == 9999)
    monkeypatch.setattr(ndhm, "_pid_running", lambda pid: False)
    monkeypatch.setattr(ndhm, "native_helper_supported", lambda: True)
    monkeypatch.setattr(ndhm, "native_helper_ready", lambda: True)
    monkeypatch.setattr(ndhm, "desktop_source_backend", lambda: "native_helper")
    monkeypatch.setattr(ndhm, "native_helper_path", lambda: Path("/tmp/ok"))

    out = ndhm.stop(state_dir=tmp_path)
    assert out["ok"] is True
    assert out["changed"] is True
    assert receipt.exists() is False
