from __future__ import annotations

from dataclasses import dataclass

import pytest

from what.asr import AsrConfig
from what.audio import AudioConfig, Chunk
from what.hallucination import is_hallucination
from what.output import OutputConfig
from what.vad import VadConfig
import what.pipeline as pipeline_mod


# --- unit: the phrase matcher ------------------------------------------------

@pytest.mark.parametrize(
    "text",
    [
        "Thanks for watching!",
        "thanks for watching",
        "  Thank you for watching.  ",
        "Please subscribe",
        "Like and subscribe",
        "Don't forget to subscribe",
        "See you in the next video",
        "Subtitles by the Amara.org community",
    ],
)
def test_flags_known_fillers(text: str):
    assert is_hallucination(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "Thank you so much for coming to the talk today.",  # contains "thank you", not equal
        "I want to thank you for watching my kids last night.",  # substring, real speech
        "Let me subscribe you to the mailing list.",
        "The next video frame arrives late.",
        "so anyway, here's the plan for the quarter",
    ],
)
def test_leaves_real_speech_alone(text: str):
    assert is_hallucination(text) is False


# --- integration: the pipeline drops flagged segments ------------------------

@dataclass
class _DummyOutput:
    events: list[dict]

    def enrich_event(self, event: dict) -> dict:
        return event

    def write_event(self, event: dict) -> None:
        self.events.append(dict(event))

    def close(self) -> None:
        return None


class _ScriptedAsr:
    """Returns a queued decode result per chunk, so a test can stage exactly which
    chunks come back as hallucinated filler versus real speech."""

    def __init__(self, results: list[dict]) -> None:
        self._results = list(results)
        self.calls = 0

    def transcribe(self, _pcm_bytes: bytes) -> dict:
        result = self._results[self.calls]
        self.calls += 1
        return result


def _seg(text: str, avg_logprob: float = -0.2) -> dict:
    return {"start": 0.0, "end": 0.5, "text": text, "avg_logprob": avg_logprob}


def _result(segments: list[dict]) -> dict:
    return {
        "text": "".join(s["text"] for s in segments).strip(),
        "segments": segments,
        "language": "en",
        "language_probability": 0.99,
        "best_avg_logprob": max((s["avg_logprob"] for s in segments), default=-0.2),
    }


def _asr_cfg() -> AsrConfig:
    return AsrConfig(
        model_size="tiny",
        compute_type="int8",
        beam_size=1,
        language="en",
        device="cpu",
        device_index=0,
        min_avg_logprob=-10.0,  # disabled: isolate the hallucination gate
        no_speech_threshold=0.5,
        logprob_threshold=-1.0,
        compression_ratio_threshold=2.4,
        condition_on_previous_text=False,
    )


def _output_cfg() -> OutputConfig:
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


def _audio_cfg() -> AudioConfig:
    return AudioConfig(
        sample_rate=16000, channels=1, frame_ms=30, chunk_ms=1000,
        overlap_ms=0, boundary_candidate_points=3,
    )


def _run(monkeypatch, results: list[dict]) -> list[dict]:
    asr = _ScriptedAsr(results)
    events: list[dict] = []
    chunks = [
        Chunk(pcm_bytes=b"\x00" * 3200, start_sec=float(i), end_sec=float(i) + 1.0, cut_samples=16000)
        for i in range(len(results))
    ]
    monkeypatch.setattr(pipeline_mod, "WhisperASR", lambda _cfg: asr)
    monkeypatch.setattr(pipeline_mod, "chunk_stream", lambda _frames, _cfg: iter(chunks))
    monkeypatch.setattr(pipeline_mod, "is_speech_chunk", lambda *a, **k: True)

    pipeline_mod._run_frames_pipeline(
        frames=[b""],
        audio_cfg=_audio_cfg(),
        vad_cfg=VadConfig(enabled=False, mode=3, speech_ratio=0.2),
        asr_cfg=_asr_cfg(),
        output_cfg=_output_cfg(),
        output=_DummyOutput(events),
        on_event=None,
        event_enricher=None,
        stats_hook=None,
        stop_event=None,
    )
    return events


def test_all_filler_chunk_emits_nothing(monkeypatch):
    events = _run(monkeypatch, [_result([_seg("Thanks for watching!")])])
    assert events == []


def test_real_speech_chunk_still_emits(monkeypatch):
    events = _run(monkeypatch, [_result([_seg(" hello there")])])
    assert len(events) == 1
    assert events[0]["text"] == "hello there"
    assert [s["text"] for s in events[0]["segments"]] == [" hello there"]


def test_mixed_chunk_keeps_only_real_segment_and_rewrites_text(monkeypatch):
    events = _run(
        monkeypatch,
        [_result([_seg(" the quarterly numbers"), _seg(" Thanks for watching!")])],
    )
    assert len(events) == 1
    seg_texts = [s["text"] for s in events[0]["segments"]]
    assert seg_texts == [" the quarterly numbers"]
    # Chunk-level text must not still carry the dropped filler.
    assert "watching" not in events[0]["text"].lower()
    assert events[0]["text"] == "the quarterly numbers"
