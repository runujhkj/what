from fastapi.testclient import TestClient

from what.service.app import create_app
from what.service.types import ServiceConfig


def _build_app():
    audio_cfg = type("AudioCfg", (), {})()
    audio_cfg.sample_rate = 16000
    audio_cfg.channels = 1
    audio_cfg.frame_ms = 30

    vad_cfg = type("VadCfg", (), {})()
    asr_cfg = type("AsrCfg", (), {})()

    output_cfg = type("OutputCfg", (), {})()
    output_cfg.jsonl_dir = "logs"
    output_cfg.text_mode = "delta"
    output_cfg.text_window_segments = 0
    output_cfg.text_window_chars = 0
    output_cfg.text_block_clear = False
    output_cfg.text_normalize = False

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
    return create_app(audio_cfg, vad_cfg, asr_cfg, output_cfg, service_cfg, "sess", "key")


def test_gpu_endpoint_schema_smoke():
    app = _build_app()
    client = TestClient(app)
    resp = client.get("/gpu")
    assert resp.status_code == 200
    payload = resp.json()
    assert "available" in payload
    assert "device" in payload
    assert "device_count" in payload
    assert "backend" in payload
    assert "reason" in payload


def test_stats_endpoint_schema_smoke():
    app = _build_app()
    client = TestClient(app)
    resp = client.get("/stats")
    assert resp.status_code == 200
    payload = resp.json()
    assert "samples" in payload
    assert "avg_rtf" in payload
    assert "avg_processing_ms" in payload
    assert "avg_audio_ms" in payload
    assert "last_update" in payload
