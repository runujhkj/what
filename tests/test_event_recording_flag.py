from types import SimpleNamespace

from what.service.pipeline import make_enricher


def _runtime():
    return SimpleNamespace(session_id="2026-09-18_001_T000000")


def test_enricher_marks_recorded_clients():
    event = {}
    make_enricher(_runtime(), "mic-abc", "mic", "e000000000000", recorded=True)(event)
    assert event == {
        "session_id": "2026-09-18_001_T000000",
        "client_id": "mic-abc",
        "input_source_id": "mic",
        "recording_epoch": "e000000000000",
        "recorded": True,
        "asr_engine": "",
        "asr_model": "",
    }


def test_enricher_defaults_to_not_recorded():
    # The HTTP ingest path does not tee audio to a WAV, so its events must say so.
    event = {}
    make_enricher(_runtime(), "http-client")(event)
    assert event["recorded"] is False


def test_enricher_records_asr_engine_and_model():
    from what.asr import AsrConfig

    runtime = _runtime()
    runtime.asr_cfg = AsrConfig(
        model_size="base", compute_type="int8", beam_size=1, language="en", device="auto",
        device_index=0, min_avg_logprob=-1.0, no_speech_threshold=0.6, logprob_threshold=-1.0,
        compression_ratio_threshold=2.4, condition_on_previous_text=False, engine="whisperkit",
    )
    event = {}
    make_enricher(runtime, "mic-abc", "mic", recorded=True)(event)
    assert (event["asr_engine"], event["asr_model"]) == ("whisperkit", "base")
