"""Exercise actual websocket ingest, WAV tee and recording metadata without a model."""
import threading
import wave
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from what.service.routes_ws import register_ws
from what.service.pipeline import make_enricher
from what.service.runtime import ServiceRuntime
from what.service.tokens import mint_token


def test_websocket_pcm_records_and_reports_audio(tmp_path, monkeypatch):
    monkeypatch.delenv("WHAT_RECORD_AUDIO", raising=False)
    runtime = ServiceRuntime(
        audio_cfg=SimpleNamespace(sample_rate=16000, channels=1, frame_ms=30),
        vad_cfg=None, asr_cfg=None,
        output_cfg=SimpleNamespace(jsonl_dir=str(tmp_path)),
        service_cfg=SimpleNamespace(ws_path="/ingest", max_clients=2),
        session_id="linux-session", session_key="test",
    )
    consumed = threading.Event()
    events = []
    def pipeline(rt, client_id, frames, log_path, stop, mode, offset, epoch, recorded):
        def work():
            try:
                for frame in frames:
                    event = {}
                    make_enricher(rt, client_id, mode, epoch, recorded)(event)
                    events.append(event)
                    consumed.set()
                    break
            finally:
                frames.close()
        thread = threading.Thread(target=work)
        thread.start()
        return thread, []
    monkeypatch.setattr("what.service.routes_ws.start_client_pipeline", pipeline)
    app = FastAPI()
    register_ws(app, runtime)
    client = TestClient(app)
    pcm = b"\x01\x00" * 480
    with client.websocket_connect("/ingest") as ws:
        ws.send_json({"client_id": "mic-test", "token": mint_token(runtime), "transport": "pcm"})
        ws.send_bytes(pcm)
        assert consumed.wait(3)
    with wave.open(str(tmp_path / "linux-session" / "mic-test.wav")) as wav:
        assert wav.readframes(480) == pcm
    assert events[0]["recorded"] is True
    assert events[0]["client_id"] == "mic-test"
    assert events[0]["session_id"] == "linux-session"
