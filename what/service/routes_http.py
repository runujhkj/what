import os
import queue
import threading
import uuid

from fastapi import FastAPI, HTTPException, Request

from ..audio import pcm_frame_generator
from .decode import start_opus_decoder
from .logs import finalize_session_log
from .pipeline import start_client_pipeline
from .runtime import ServiceRuntime
from .tokens import consume_token
from .types import ClientState
from ..streaming import pcm_frames_from_queue


def register_http(app: FastAPI, runtime: ServiceRuntime) -> None:
    @app.post(runtime.service_cfg.http_path)
    async def ingest_http(request: Request) -> dict[str, str]:
        if len(runtime.clients) >= runtime.service_cfg.max_clients:
            raise HTTPException(status_code=429, detail="busy")

        params = request.query_params
        transport = params.get("transport", "pcm")
        client_id = params.get("client_id") or f"client-{uuid.uuid4().hex[:8]}"
        if client_id in runtime.clients:
            raise HTTPException(status_code=409, detail="client_id in use")
        token = params.get("token", "")
        if not consume_token(runtime, token):
            raise HTTPException(status_code=403, detail="unauthorized")

        session_dir = os.path.join(runtime.output_cfg.jsonl_dir, runtime.session_id)
        os.makedirs(session_dir, exist_ok=True)
        log_path = os.path.join(session_dir, f"{client_id}.jsonl")

        stop_event = threading.Event()
        frame_samples = int(runtime.audio_cfg.sample_rate * runtime.audio_cfg.frame_ms / 1000)
        decoder_proc = None

        try:
            if transport == "pcm":
                data_queue: queue.Queue[bytes] = queue.Queue()
                frames = pcm_frames_from_queue(data_queue, frame_samples, stop_event=stop_event)
                thread, transcript = start_client_pipeline(runtime, client_id, frames, log_path, stop_event)
                runtime.clients[client_id] = ClientState(
                    client_id=client_id,
                    transport=transport,
                    stop_event=stop_event,
                    thread=thread,
                    queue=data_queue,
                    decoder_proc=None,
                    log_path=log_path,
                    session_dir=session_dir,
                    transcript=transcript,
                )

                async for chunk in request.stream():
                    data_queue.put(chunk)
            elif transport == "opus":
                decoder_proc = start_opus_decoder(runtime.audio_cfg)
                frames = pcm_frame_generator(decoder_proc, frame_samples)
                thread, transcript = start_client_pipeline(runtime, client_id, frames, log_path, stop_event)
                runtime.clients[client_id] = ClientState(
                    client_id=client_id,
                    transport=transport,
                    stop_event=stop_event,
                    thread=thread,
                    queue=None,
                    decoder_proc=decoder_proc,
                    log_path=log_path,
                    session_dir=session_dir,
                    transcript=transcript,
                )

                async for chunk in request.stream():
                    assert decoder_proc.stdin is not None
                    decoder_proc.stdin.write(chunk)
            else:
                raise HTTPException(status_code=400, detail="unsupported transport")
        finally:
            state = runtime.clients.pop(client_id, None)
            if state is None:
                return {"status": "ok"}
            state.stop_event.set()
            if state.queue is not None:
                state.queue.put(b"")
            if state.decoder_proc is not None:
                if state.decoder_proc.stdin is not None:
                    state.decoder_proc.stdin.close()
                state.decoder_proc.terminate()
            if state.thread.is_alive():
                state.thread.join(timeout=2)
            finalize_session_log(
                state.log_path,
                state.session_dir,
                runtime.output_cfg.jsonl_dir,
                state.transcript,
            )
        return {"status": "ok", "client_id": client_id}
