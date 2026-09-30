import asyncio
import json
import os
import queue
import sys
import threading
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from ..audio import pcm_frame_generator
from .decode import start_opus_decoder
from .pipeline import start_client_pipeline
from .recording import recording_duration_sec, recording_enabled, tee_frames_to_wav
from .runtime import ServiceRuntime
from .tokens import consume_token
from .types import ClientState
from ..streaming import pcm_frames_from_queue


def register_ws(app: FastAPI, runtime: ServiceRuntime) -> None:
    @app.websocket(runtime.service_cfg.ws_path)
    async def ingest(ws: WebSocket) -> None:
        if len(runtime.clients) >= runtime.service_cfg.max_clients:
            await ws.close(code=1013)
            return
        await ws.accept()

        try:
            start_msg = await ws.receive_text()
            start = json.loads(start_msg)
        except Exception:
            sys.stderr.write("ingest close 1008: invalid start frame (non-JSON start message)\n")
            sys.stderr.flush()
            await ws.close(code=1008, reason="invalid_start_frame")
            return

        transport = start.get("transport", "pcm")
        client_id = start.get("client_id") or f"client-{uuid.uuid4().hex[:8]}"
        input_mode = start.get("input_mode") or "mic"
        sample_rate = int(start.get("sample_rate", runtime.audio_cfg.sample_rate))
        channels = int(start.get("channels", runtime.audio_cfg.channels))

        if client_id in runtime.clients:
            sys.stderr.write(f"ingest close 1008: duplicate client_id={client_id}\n")
            sys.stderr.flush()
            await ws.close(code=1008, reason="duplicate_client_id")
            return
        token = start.get("token", "")
        if not consume_token(runtime, token):
            sys.stderr.write("ingest close 1008: invalid/expired pairing token\n")
            sys.stderr.flush()
            await ws.close(code=1008, reason="invalid_or_expired_token")
            return

        if transport == "pcm":
            if sample_rate != runtime.audio_cfg.sample_rate or channels != runtime.audio_cfg.channels:
                sys.stderr.write(
                    "ingest close 1008: pcm format mismatch "
                    f"(client sr={sample_rate} ch={channels}, "
                    f"service sr={runtime.audio_cfg.sample_rate} ch={runtime.audio_cfg.channels})\n"
                )
                sys.stderr.flush()
                await ws.close(code=1008, reason="pcm_format_mismatch")
                return

        session_dir = os.path.join(runtime.output_cfg.jsonl_dir, runtime.session_id)
        os.makedirs(session_dir, exist_ok=True)
        log_path = os.path.join(session_dir, f"{client_id}.jsonl")
        # Session recording (default on): sample 0 aligns with the first pipeline frame, so
        # WAV offsets == segment/word abs_start seconds -- the basis for click-to-replay and
        # the correction corpus. Companion to <client_id>.jsonl in the same session dir.
        wav_path = os.path.join(session_dir, f"{client_id}.wav")
        record = recording_enabled()
        sys.stderr.write(
            f"recording: client={client_id} enabled={record} path={os.path.abspath(wav_path)}\n"
        )
        sys.stderr.flush()
        timeline_offset_sec = recording_duration_sec(
            wav_path, runtime.audio_cfg.sample_rate, runtime.audio_cfg.channels) if record else 0.0
        # IDs must remain unique in the append-only JSONL. The offset is sample-derived,
        # so it also gives review playback a stable epoch that maps to this WAV exactly.
        recording_epoch = f"e{int(timeline_offset_sec * runtime.audio_cfg.sample_rate):012d}"

        stop_event = threading.Event()
        decoder_proc = None
        frame_samples = int(runtime.audio_cfg.sample_rate * runtime.audio_cfg.frame_ms / 1000)

        try:
            if transport == "pcm":
                data_queue: queue.Queue[bytes] = queue.Queue()
                frames = pcm_frames_from_queue(data_queue, frame_samples, stop_event=stop_event)
                if record:
                    frames = tee_frames_to_wav(
                        frames, wav_path, runtime.audio_cfg.sample_rate, runtime.audio_cfg.channels)
                # Build the ASR worker OFF the event loop: creating WhisperASR can load/download a
                # model for seconds (slow first-run faster_whisper on CPU), and doing that
                # synchronously here blocked the loop past the WS ping timeout -> the ingest
                # dropped with 1006 before any error. asyncio.to_thread keeps the loop alive.
                thread, transcript = await asyncio.to_thread(
                    start_client_pipeline, runtime, client_id, frames, log_path, stop_event, input_mode,
                    timeline_offset_sec, recording_epoch, record)
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

                while True:
                    data = await ws.receive_bytes()
                    data_queue.put(data)
            elif transport == "opus":
                decoder_proc = start_opus_decoder(runtime.audio_cfg)
                frames = pcm_frame_generator(decoder_proc, frame_samples)
                if record:
                    frames = tee_frames_to_wav(
                        frames, wav_path, runtime.audio_cfg.sample_rate, runtime.audio_cfg.channels)
                # Build the ASR worker OFF the event loop: creating WhisperASR can load/download a
                # model for seconds (slow first-run faster_whisper on CPU), and doing that
                # synchronously here blocked the loop past the WS ping timeout -> the ingest
                # dropped with 1006 before any error. asyncio.to_thread keeps the loop alive.
                thread, transcript = await asyncio.to_thread(
                    start_client_pipeline, runtime, client_id, frames, log_path, stop_event, input_mode,
                    timeline_offset_sec, recording_epoch, record)
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

                while True:
                    data = await ws.receive_bytes()
                    assert decoder_proc.stdin is not None
                    decoder_proc.stdin.write(data)
            else:
                sys.stderr.write(f"ingest close 1008: unsupported transport={transport}\n")
                sys.stderr.flush()
                await ws.close(code=1008, reason="unsupported_transport")
                return
        except WebSocketDisconnect:
            pass
        except Exception as exc:
            # Any non-disconnect error here otherwise propagates without a clear log and the
            # client just sees an abnormal 1006. Log it explicitly so the cause is visible.
            import traceback
            sys.stderr.write(
                f"ingest handler error (client_id={client_id}): {exc!r}\n{traceback.format_exc()}\n")
            sys.stderr.flush()
        finally:
            state = runtime.clients.pop(client_id, None)
            if state is None:
                return
            state.stop_event.set()
            if state.queue is not None:
                state.queue.put(b"")
            if state.decoder_proc is not None:
                if state.decoder_proc.stdin is not None:
                    state.decoder_proc.stdin.close()
                state.decoder_proc.terminate()
            if state.thread.is_alive():
                state.thread.join(timeout=2)
            # Keep a client's live JSONL in place across reconnects. The companion WAV
            # appends on reconnect and the pipeline offsets new word times by its durable
            # sample length; renaming the JSONL here made the review UI retain old spans
            # while the next client created a fresh, shorter log at the same path. That
            # mapped a post-restart click back into earlier recording audio.
