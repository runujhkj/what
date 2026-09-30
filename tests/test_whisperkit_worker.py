import os
from types import SimpleNamespace

import pytest

from what.whisperkit_worker import WhisperKitWorkerASR, _check_bundled_build


def test_bundled_worker_requires_rebuild_after_source_update(tmp_path):
    sources = tmp_path / "Sources"
    sources.mkdir()
    source = sources / "main.swift"
    source.write_text("// new offline startup implementation")
    worker = tmp_path / "worker"
    worker.write_text("old binary")
    os.utime(worker, ns=(100, 100))
    os.utime(source, ns=(200, 200))
    with pytest.raises(RuntimeError, match="swift build -c release"):
        _check_bundled_build(worker, tmp_path)

    os.utime(worker, ns=(300, 300))
    _check_bundled_build(worker, tmp_path)


def test_bundled_worker_requires_rebuild_after_dependency_update(tmp_path):
    worker = tmp_path / "worker"
    worker.write_text("binary")
    lockfile = tmp_path / "Package.resolved"
    lockfile.write_text("{}")
    os.utime(worker, ns=(100, 100))
    os.utime(lockfile, ns=(200, 200))
    with pytest.raises(RuntimeError, match="older than its source"):
        _check_bundled_build(worker, tmp_path)


def test_missing_build_keeps_existing_startup_diagnostic(tmp_path):
    _check_bundled_build(tmp_path / "missing", tmp_path)


def test_custom_worker_paths_do_not_require_checkout_build(monkeypatch):
    worker = object.__new__(WhisperKitWorkerASR)
    worker.cfg = SimpleNamespace(worker_path="/custom/worker")
    monkeypatch.setenv("WHAT_WHISPERKIT_WORKER", "/environment/worker")
    assert worker._worker_path() == "/custom/worker"
    worker.cfg.worker_path = None
    assert worker._worker_path() == "/environment/worker"
