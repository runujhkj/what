from dataclasses import replace

import pytest

from what.asr import AsrConfig, create_asr_engine, resolve_engine_name


def _cfg(**overrides) -> AsrConfig:
    base = AsrConfig(
        model_size="small",
        compute_type="int8",
        beam_size=1,
        language="en",
        device="cpu",
        device_index=0,
        min_avg_logprob=-1.0,
        no_speech_threshold=0.6,
        logprob_threshold=-1.0,
        compression_ratio_threshold=2.4,
        condition_on_previous_text=False,
    )
    return replace(base, **overrides)


def test_explicit_engine_is_not_platform_dependent():
    assert resolve_engine_name(_cfg(engine="whisper_cpp")) == "whisper_cpp"


def test_unknown_engine_is_rejected():
    with pytest.raises(ValueError, match="unsupported ASR engine"):
        create_asr_engine(_cfg(engine="not-an-engine"))
