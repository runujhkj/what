from __future__ import annotations

from dataclasses import dataclass

import pytest

from what.asr import AsrConfig
from what.audio import AudioConfig, Chunk
from what.output import OutputConfig
from what.vad import VadConfig
import what.pipeline as pipeline_mod


@dataclass
class _DummyOutput:
    events: list[dict]

    def enrich_event(self, event: dict) -> dict:
        return event

    def write_event(self, event: dict) -> None:
        self.events.append(dict(event))

    def close(self) -> None:
        return None


class _DummyAsr:
    def __init__(self, _cfg: AsrConfig) -> None:
        self.calls = 0

    def transcribe(self, _pcm_bytes: bytes) -> dict:
        self.calls += 1
        return {
            "text": f"seg-{self.calls}",
            "segments": [
                {
                    "start": 0.0,
                    "end": 0.5,
                    "text": f"seg-{self.calls}",
                    "avg_logprob": -0.2,
                }
            ],
            "language": "en",
            "language_probability": 0.99,
            "best_avg_logprob": -0.2,
        }


def _make_asr_cfg() -> AsrConfig:
    return AsrConfig(
        model_size="tiny",
        compute_type="int8",
        beam_size=1,
        language="en",
        device="cpu",
        device_index=0,
        min_avg_logprob=-10.0,
        no_speech_threshold=0.5,
        logprob_threshold=-1.0,
        compression_ratio_threshold=2.4,
        condition_on_previous_text=False,
    )


def _make_output_cfg() -> OutputConfig:
    return OutputConfig(
        text_stream=False,
        jsonl_log="",
        jsonl_dir="",
        text_mode="delta",
        text_window_segments=0,
        text_window_chars=0,
        text_block_clear=False,
        text_normalize=False,
    )


def _make_audio_cfg(chunk_ms: int = 1000) -> AudioConfig:
    return AudioConfig(
        sample_rate=16000,
        channels=1,
        frame_ms=30,
        chunk_ms=chunk_ms,
        overlap_ms=0,
        boundary_candidate_points=3,
    )


def _run_pipeline_with_chunks(
    monkeypatch: pytest.MonkeyPatch,
    chunks: list[Chunk],
    *,
    vad_enabled: bool = True,
    speech_detected: bool = True,
) -> tuple[_DummyAsr, _DummyOutput, list[dict]]:
    asr_holder: dict[str, _DummyAsr] = {}
    output_events: list[dict] = []
    callback_events: list[dict] = []

    def _make_asr(cfg: AsrConfig) -> _DummyAsr:
        inst = _DummyAsr(cfg)
        asr_holder["inst"] = inst
        return inst

    def _make_output(_cfg: OutputConfig) -> _DummyOutput:
        return _DummyOutput(output_events)

    def _chunk_stream(_frames, _audio_cfg):
        return iter(chunks)

    tick = {"n": 0}

    def _perf_counter() -> float:
        # First call seeds pipeline start at t=0. Subsequent calls simulate
        # processing far into wall-clock time to trigger lag paths.
        tick["n"] += 1
        return 0.0 if tick["n"] == 1 else 10.0

    monkeypatch.setattr(pipeline_mod, "WhisperASR", _make_asr)
    monkeypatch.setattr(pipeline_mod, "OutputManager", _make_output)
    monkeypatch.setattr(pipeline_mod, "chunk_stream", _chunk_stream)
    monkeypatch.setattr(pipeline_mod, "is_speech_chunk", lambda *args, **kwargs: speech_detected)
    monkeypatch.setattr(pipeline_mod.time, "perf_counter", _perf_counter)

    pipeline_mod._run_frames_pipeline(
        frames=[b""],
        audio_cfg=_make_audio_cfg(),
        vad_cfg=VadConfig(enabled=vad_enabled, mode=3, speech_ratio=0.2),
        asr_cfg=_make_asr_cfg(),
        output_cfg=_make_output_cfg(),
        output=_DummyOutput(output_events),
        on_event=lambda e: callback_events.append(dict(e)),
        event_enricher=None,
        stats_hook=None,
        stop_event=None,
    )
    return asr_holder["inst"], _DummyOutput(output_events), callback_events


def test_stale_chunk_drop_skips_decode_under_lag_when_enabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WHAT_DROP_STALE_CHUNKS", "1")
    monkeypatch.setenv("WHAT_MAX_PROCESSING_LAG_SEC", "3")
    monkeypatch.setenv("WHAT_SKIP_SUBCHUNKS_WHEN_LAGGED", "0")

    chunks = [
        Chunk(pcm_bytes=b"\x00" * 3200, start_sec=0.0, end_sec=1.0, cut_samples=16000),
        Chunk(pcm_bytes=b"\x00" * 3200, start_sec=1.0, end_sec=2.0, cut_samples=16000),
    ]
    asr, _output, events = _run_pipeline_with_chunks(monkeypatch, chunks, vad_enabled=True)
    assert asr.calls == 0
    assert events == []


def test_stale_drop_escape_hatch_forces_decode_so_stream_never_goes_mute(
    monkeypatch: pytest.MonkeyPatch,
):
    # Regression: a sustained lag above the cap used to drop EVERY chunk forever (the mic
    # went permanently silent after one contention spike). The escape hatch must force a
    # decode every force_decode_every_chunks so captions keep coming and the stream recovers.
    monkeypatch.setenv("WHAT_DROP_STALE_CHUNKS", "1")
    monkeypatch.setenv("WHAT_MAX_PROCESSING_LAG_SEC", "3")
    monkeypatch.setenv("WHAT_SKIP_SUBCHUNKS_WHEN_LAGGED", "0")
    monkeypatch.setenv("WHAT_FORCE_DECODE_EVERY_CHUNKS", "4")

    # Five full 1.0s chunks, all lagged (harness wall-clock is pinned at 10s).
    chunks = [
        Chunk(pcm_bytes=b"\x00" * 3200, start_sec=float(i), end_sec=float(i + 1), cut_samples=16000)
        for i in range(5)
    ]
    asr, _output, events = _run_pipeline_with_chunks(monkeypatch, chunks, vad_enabled=True)
    # The 4th chunk (chunks_since_decode == force_decode_every_chunks) is forced through.
    assert asr.calls >= 1, "escape hatch must force at least one decode under sustained lag"
    assert events, "captions must keep flowing instead of going permanently mute"


def test_stale_chunk_drop_disabled_allows_decode_under_lag(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WHAT_DROP_STALE_CHUNKS", "0")
    monkeypatch.setenv("WHAT_MAX_PROCESSING_LAG_SEC", "3")
    monkeypatch.setenv("WHAT_SKIP_SUBCHUNKS_WHEN_LAGGED", "0")

    chunks = [
        Chunk(pcm_bytes=b"\x00" * 3200, start_sec=0.0, end_sec=1.0, cut_samples=16000),
        Chunk(pcm_bytes=b"\x00" * 3200, start_sec=1.0, end_sec=2.0, cut_samples=16000),
    ]
    asr, _output, events = _run_pipeline_with_chunks(monkeypatch, chunks, vad_enabled=True)
    assert asr.calls == 2
    assert len(events) == 2


def test_skip_short_subchunks_when_lagged(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WHAT_DROP_STALE_CHUNKS", "1")
    monkeypatch.setenv("WHAT_MAX_PROCESSING_LAG_SEC", "999")
    monkeypatch.setenv("WHAT_SKIP_SUBCHUNKS_WHEN_LAGGED", "1")
    monkeypatch.setenv("WHAT_SUBCHUNK_LAG_SEC", "1")
    monkeypatch.setenv("WHAT_SUBCHUNK_MIN_RATIO", "0.9")

    chunks = [
        # 0.5s chunk (< 1.0 * 0.9) should be skipped under lag.
        Chunk(pcm_bytes=b"\x00" * 3200, start_sec=0.0, end_sec=0.5, cut_samples=8000),
        # 1.0s chunk should pass.
        Chunk(pcm_bytes=b"\x00" * 3200, start_sec=0.5, end_sec=1.5, cut_samples=16000),
    ]
    asr, _output, events = _run_pipeline_with_chunks(monkeypatch, chunks, vad_enabled=True)
    assert asr.calls == 1
    assert len(events) == 1


def test_stale_drop_expected_to_apply_with_vad_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WHAT_DROP_STALE_CHUNKS", "1")
    monkeypatch.setenv("WHAT_MAX_PROCESSING_LAG_SEC", "3")
    monkeypatch.setenv("WHAT_SKIP_SUBCHUNKS_WHEN_LAGGED", "0")

    chunks = [
        Chunk(pcm_bytes=b"\x00" * 3200, start_sec=0.0, end_sec=1.0, cut_samples=16000),
    ]
    asr, _output, events = _run_pipeline_with_chunks(monkeypatch, chunks, vad_enabled=False)
    assert asr.calls == 0
    assert events == []


def test_dynamic_decode_simplification_skips_under_heavier_lag(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WHAT_DROP_STALE_CHUNKS", "1")
    monkeypatch.setenv("WHAT_MAX_PROCESSING_LAG_SEC", "999")
    monkeypatch.setenv("WHAT_SKIP_SUBCHUNKS_WHEN_LAGGED", "0")
    monkeypatch.setenv("WHAT_DYNAMIC_DECODE_SIMPLIFY", "1")
    monkeypatch.setenv("WHAT_DYNAMIC_SIMPLIFY_LAG_SEC", "2")
    monkeypatch.setenv("WHAT_SUBCHUNK_MIN_RATIO", "0.8")

    chunks = [
        # With lag=8s in fixture perf counter, this 0.83s chunk should be
        # dropped by dynamic simplify (ratio > 0.8 under severity uplift).
        Chunk(pcm_bytes=b"\x00" * 3200, start_sec=0.0, end_sec=0.83, cut_samples=13280),
        # This full-size chunk should still decode.
        Chunk(pcm_bytes=b"\x00" * 3200, start_sec=0.83, end_sec=1.83, cut_samples=16000),
    ]
    asr, _output, events = _run_pipeline_with_chunks(monkeypatch, chunks, vad_enabled=True)
    assert asr.calls == 1
    assert len(events) == 1
    lag = events[0].get("lag") or {}
    assert int(lag.get("dropped_dynamic_total", 0)) >= 1


def test_event_contains_lag_telemetry_fields(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WHAT_DROP_STALE_CHUNKS", "0")
    monkeypatch.setenv("WHAT_SKIP_SUBCHUNKS_WHEN_LAGGED", "0")
    monkeypatch.setenv("WHAT_DYNAMIC_DECODE_SIMPLIFY", "0")

    chunks = [
        Chunk(pcm_bytes=b"\x00" * 3200, start_sec=0.0, end_sec=1.0, cut_samples=16000),
    ]
    asr, _output, events = _run_pipeline_with_chunks(monkeypatch, chunks, vad_enabled=True)
    assert asr.calls == 1
    assert len(events) == 1
    lag = events[0].get("lag")
    assert isinstance(lag, dict)
    assert "processing_lag_sec" in lag
    assert "decode_audio_ratio_avg" in lag
    assert "chunks_seen_total" in lag
    assert "chunks_decoded_total" in lag
    assert "dropped_stale_total" in lag
    assert "dropped_subchunk_total" in lag
    assert "dropped_dynamic_total" in lag
    assert "vad_reject_total" in lag
    assert "vad_forced_decode_total" in lag


def test_lag_snapshot_is_logged_when_vad_rejects_every_chunk(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setenv("WHAT_DROP_STALE_CHUNKS", "0")
    monkeypatch.setenv("WHAT_FORCE_DECODE_ON_VAD_REJECT", "0")
    monkeypatch.setenv("WHAT_LAG_TELEMETRY_EVERY_CHUNKS", "2")

    chunks = [
        Chunk(pcm_bytes=b"\x00" * 3200, start_sec=float(i), end_sec=float(i + 1), cut_samples=16000)
        for i in range(2)
    ]
    asr, _output, events = _run_pipeline_with_chunks(monkeypatch, chunks, vad_enabled=True, speech_detected=False)

    assert asr.calls == 0
    assert events == []
    stderr = capsys.readouterr().err
    assert "lag telemetry: stream=mic" in stderr
    assert "seen=2" in stderr
    assert "vad_reject=2" in stderr


def test_force_decode_on_vad_reject_prevents_starvation(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WHAT_DROP_STALE_CHUNKS", "0")
    monkeypatch.setenv("WHAT_FORCE_DECODE_ON_VAD_REJECT", "1")
    monkeypatch.setenv("WHAT_FORCE_DECODE_ON_VAD_REJECT_EVERY_CHUNKS", "2")

    chunks = [
        Chunk(pcm_bytes=b"\x00" * 3200, start_sec=0.0, end_sec=1.0, cut_samples=16000),
        Chunk(pcm_bytes=b"\x00" * 3200, start_sec=1.0, end_sec=2.0, cut_samples=16000),
        Chunk(pcm_bytes=b"\x00" * 3200, start_sec=2.0, end_sec=3.0, cut_samples=16000),
        Chunk(pcm_bytes=b"\x00" * 3200, start_sec=3.0, end_sec=4.0, cut_samples=16000),
    ]
    asr, _output, events = _run_pipeline_with_chunks(monkeypatch, chunks, vad_enabled=True, speech_detected=False)
    assert asr.calls == 2
    assert len(events) == 2
    lag = events[-1].get("lag") or {}
    assert int(lag.get("vad_reject_total", 0)) >= 2
    assert int(lag.get("vad_forced_decode_total", 0)) >= 1
