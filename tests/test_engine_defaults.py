from argparse import Namespace

import pytest

from what.cli.builders import apply_engine_defaults, build_asr_cfg, build_audio_cfg
from what.config import load_config


def _args(**overrides) -> Namespace:
    fields = dict(
        model=None, compute_type=None, beam_size=None, lang=None, device=None,
        device_index=None, no_speech_threshold=None, logprob_threshold=None,
        compression_ratio_threshold=None, condition_on_previous_text=False,
        engine=None, model_path=None, worker_path=None,
        frame_ms=None, chunk_ms=None, overlap_ms=None, boundary_candidate_points=None,
    )
    fields.update(overrides)
    return Namespace(**fields)


@pytest.fixture(autouse=True)
def _no_env_overrides(monkeypatch):
    for key in ("WHAT_SERVICE_MODEL", "WHAT_SERVICE_DEVICE", "WHAT_SERVICE_ENGINE",
                "WHAT_SERVICE_COMPUTE_TYPE", "WHAT_SERVICE_MODEL_PATH"):
        monkeypatch.delenv(key, raising=False)


def _built(args):
    cfg = load_config("config/default.toml")
    audio_cfg = build_audio_cfg(args, cfg)
    asr_cfg = build_asr_cfg(args, cfg)
    apply_engine_defaults(args, cfg, audio_cfg, asr_cfg)
    return audio_cfg, asr_cfg


def test_whisperkit_replaces_cuda_tuned_defaults():
    audio_cfg, asr_cfg = _built(_args(engine="whisperkit"))
    assert asr_cfg.model_size == "base"
    assert asr_cfg.device == "auto"
    assert audio_cfg.chunk_ms == 2500


def test_whisperkit_keeps_explicit_choices():
    audio_cfg, asr_cfg = _built(_args(engine="whisperkit", model="small", device="cpu", chunk_ms=1200))
    assert asr_cfg.model_size == "small"
    assert asr_cfg.device == "cpu"
    assert audio_cfg.chunk_ms == 1200


def test_whisperkit_keeps_environment_model(monkeypatch):
    monkeypatch.setenv("WHAT_SERVICE_MODEL", "large-v3")
    _, asr_cfg = _built(_args(engine="whisperkit"))
    assert asr_cfg.model_size == "large-v3"


def test_faster_whisper_uses_shared_2500ms_chunk_default():
    # faster-whisper now shares WhisperKit's 2500 ms chunk length so Linux/Windows get the
    # same full-utterance context (and fewer near-silence hallucinations) as macOS.
    audio_cfg, asr_cfg = _built(_args(engine="faster_whisper"))
    assert asr_cfg.model_size == "medium"
    assert asr_cfg.device == "cuda"
    assert audio_cfg.chunk_ms == 2500
