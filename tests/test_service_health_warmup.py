"""/health answers as soon as the port binds and reports ASR warmup state separately, so
a slow first model load reads as "loading" instead of a refused connection."""
from fastapi.testclient import TestClient

from what.service.app import create_app
from what.service.types import ServiceConfig


def _build_app(*, warm_in_background: bool):
    audio_cfg = type("AudioCfg", (), {})()
    audio_cfg.sample_rate = 16000
    audio_cfg.channels = 1
    audio_cfg.frame_ms = 30
    vad_cfg = type("VadCfg", (), {})()
    asr_cfg = type("AsrCfg", (), {})()
    output_cfg = type("OutputCfg", (), {})()
    output_cfg.jsonl_dir = "logs"
    service_cfg = ServiceConfig(
        host="127.0.0.1",
        port=8765,
        sse_path="/events",
        ws_path="/ingest",
        http_path="/ingest-http",
        pair_path="/pair",
        local_pair=True,
        mdns_name="what",
        mdns_enabled=False,
        advertise_host=None,
        max_clients=1,
    )
    return create_app(
        audio_cfg, vad_cfg, asr_cfg, output_cfg, service_cfg, "sess", "key",
        warm_in_background=warm_in_background,
    )


def test_health_ok_and_asr_ready_without_background_warmup():
    app = _build_app(warm_in_background=False)
    with TestClient(app) as client:  # context manager runs the lifespan
        payload = client.get("/health").json()
    assert payload["status"] == "ok"
    assert payload["asr"] == "ready"


def test_health_reports_loading_while_background_warmup_runs(monkeypatch):
    # Simulate a warmup that has started but not finished: the port is up and /health
    # answers, with asr reported as "loading" rather than the request failing.
    def _leave_loading(runtime):
        runtime.asr_status = "loading"  # started, event stays unset

    import what.service.lifecycle as lifecycle
    monkeypatch.setattr(lifecycle, "warm_up_in_background", _leave_loading)

    app = _build_app(warm_in_background=True)
    with TestClient(app) as client:
        payload = client.get("/health").json()
    assert payload["status"] == "ok"
    assert payload["asr"] == "loading"
