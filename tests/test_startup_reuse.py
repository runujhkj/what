from types import SimpleNamespace

import pytest

from what.controller import routes_cleanup
from what.service import pipeline as service_pipeline
from what.service.runtime import ServiceRuntime


def _runtime(spare=None):
    return ServiceRuntime(
        audio_cfg=None, vad_cfg=None, asr_cfg=SimpleNamespace(), output_cfg=None,
        service_cfg=None, session_id="s", session_key="s", spare_asr=spare,
    )


def test_first_stream_reuses_preflight_worker(monkeypatch):
    created = []
    monkeypatch.setattr(service_pipeline, "WhisperASR", lambda cfg: created.append(cfg) or object())
    spare = object()
    runtime = _runtime(spare)

    first, _ = service_pipeline.get_stream_worker(runtime, "desktop")
    assert first is spare and runtime.spare_asr is None and created == []

    second, _ = service_pipeline.get_stream_worker(runtime, "mic")
    assert second is not spare and len(created) == 1
    assert runtime.shared_asr is second  # the mic worker stays the shared/back-compat one

    again, _ = service_pipeline.get_stream_worker(runtime, "desktop")
    assert again is first and len(created) == 1


def test_without_spare_each_stream_loads_its_own(monkeypatch):
    monkeypatch.setattr(service_pipeline, "WhisperASR", lambda cfg: object())
    runtime = _runtime()
    mic, _ = service_pipeline.get_stream_worker(runtime, "mic")
    desk, _ = service_pipeline.get_stream_worker(runtime, "desktop")
    assert mic is not desk


@pytest.mark.parametrize("value,expected", [("", False), ("0", False), ("1", True), ("true", True), ("on", True)])
def test_llm_cleanup_preload_is_opt_in(monkeypatch, value, expected):
    monkeypatch.setenv("WHAT_LLM_CLEANUP_PRELOAD", value)
    assert routes_cleanup._preload_requested() is expected
