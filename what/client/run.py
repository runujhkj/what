import asyncio
import json
import sys
import threading
import uuid

import websockets

from ..audio import AudioConfig, InputConfig
from ..live_audio_meter import LiveAudioMeter
from .dead_input import DeadInputDetector
from ..live_audio import describe_live_capture_graph
from ..live_audio_probe import measure_live_sources, probe_live_sources
from .capture import start_capture
from .devices import print_desktop_info, print_mic_info
from .stream import audio_generator
from .types import ClientConfig
from ..discovery import discover_services
from ..view import view_sse


def _ffmpeg_stderr_forwarder(proc, stop_event: threading.Event) -> None:
    stream = getattr(proc, "stderr", None)
    if stream is None:
        return
    suppressed = (
        "Error submitting a packet to the muxer",
        "Error muxing a packet",
        "Immediate exit requested",
        "Broken pipe",
        "Error writing trailer",
        "Error closing file",
        "Terminating thread with return code",
        "Task finished with error code",
    )
    while True:
        line = stream.readline()
        if not line:
            return
        text = line.decode("utf-8", errors="replace")
        if stop_event.is_set() and any(token in text for token in suppressed):
            continue
        sys.stderr.write(text)
        sys.stderr.flush()


async def run_client(
    client_cfg: ClientConfig,
    input_cfg: InputConfig,
    audio_cfg: AudioConfig,
    token: str,
    client_name: str | None,
    captions_on: bool,
    captions_mode: str = "delta",
    captions_block_clear: bool = False,
    captions_normalize: bool = True,
    transcript_prefix: str | None = None,
    event_prefix: str | None = None,
) -> None:
    host = client_cfg.target_host
    port = client_cfg.target_port
    if not host:
        services = await asyncio.to_thread(discover_services)
        if not services:
            raise RuntimeError("No what service discovered on LAN")
        first = next(iter(services.values()))
        host = first.host
        port = first.port

    client_id = client_name or f"client-{uuid.uuid4().hex[:8]}"
    ws_url = f"ws://{host}:{port}{client_cfg.target_ws_path}"
    sse_url = f"http://{host}:{port}{client_cfg.target_sse_path}"

    if input_cfg.mic_enabled:
        print_mic_info(input_cfg)
    if input_cfg.desktop_enabled:
        print_desktop_info(input_cfg)
    active_sources = []
    if input_cfg.mic_enabled:
        active_sources.append("mic")
    if input_cfg.desktop_enabled:
        active_sources.append("desktop")
    if active_sources:
        sys.stderr.write(f"capture sources: {', '.join(active_sources)}\n")
        sys.stderr.flush()
    inputs, mixed, mode = describe_live_capture_graph(input_cfg)
    sys.stderr.write(
        f"capture graph: inputs={inputs} mixed={'yes' if mixed else 'no'} mode={mode}\n"
    )
    sys.stderr.flush()
    if active_sources:
        probe = probe_live_sources(input_cfg, audio_cfg)
        probe_line = " ".join(
            f"{name}={probe.get(name, 'off')}" for name in ("mic", "desktop") if name in probe
        )
        if probe_line:
            sys.stderr.write(f"capture probe: {probe_line}\n")
            sys.stderr.flush()
        try:
            probe_detail = measure_live_sources(input_cfg, audio_cfg, duration_sec=0.35)
            desk = probe_detail.get("desktop") if isinstance(probe_detail, dict) else None
            if isinstance(desk, dict):
                state = str(desk.get("state", ""))
                if state in {"silent", "error"}:
                    code = desk.get("code")
                    nbytes = desk.get("bytes")
                    peak = desk.get("peak")
                    avg_abs = desk.get("avg_abs")
                    rms = desk.get("rms")
                    stderr = str(desk.get("stderr") or "").strip()
                    detail = (
                        f"capture probe detail: desktop_state={state}"
                        f" code={code if code is not None else ''}"
                        f" bytes={nbytes if nbytes is not None else ''}"
                        f" peak={peak if peak is not None else ''}"
                        f" avg_abs={avg_abs if avg_abs is not None else ''}"
                        f" rms={rms if rms is not None else ''}"
                    )
                    if stderr:
                        detail += f" stderr={stderr}"
                    sys.stderr.write(detail + "\n")
                    sys.stderr.flush()
        except Exception as err:
            sys.stderr.write(f"capture probe detail warning: {err}\n")
            sys.stderr.flush()

    try:
        proc = start_capture(input_cfg, audio_cfg, client_cfg.transport)
    except Exception as err:
        sys.stderr.write(f"capture start failed: {err}\n")
        sys.stderr.flush()
        raise
    stop_event = threading.Event()
    captions_thread = None
    meter = None
    chunks_sent = 0
    ffmpeg_stderr_thread = threading.Thread(
        target=_ffmpeg_stderr_forwarder,
        args=(proc, stop_event),
        daemon=True,
    )
    ffmpeg_stderr_thread.start()
    if active_sources:
        meter = LiveAudioMeter(input_cfg, audio_cfg, stop_event)
        meter.start()

    if captions_on:
        captions_thread = threading.Thread(
            target=view_sse,
            kwargs={
                "url": sse_url,
                "client_id": client_id,
                "session_id": None,
                "raw": False,
                "display_mode": captions_mode,
                "block_clear": captions_block_clear,
                "normalize": captions_normalize,
                "transcript_prefix": transcript_prefix,
                "event_prefix": event_prefix,
                "stop_event": stop_event,
            },
            daemon=True,
        )
        captions_thread.start()

    try:
        async with websockets.connect(ws_url, max_queue=None) as ws:
            if getattr(input_cfg, "stream_tag", None):
                # Explicit override: a launcher feeding this client via stdin still wants it
                # tagged as its true stream (e.g. mic single-capture fan-out).
                _input_mode = input_cfg.stream_tag
            elif input_cfg.mode == "stdin":
                # stdin = system/desktop audio tap; route events to the desktop lane
                _input_mode = "desktop"
            elif input_cfg.desktop_enabled and input_cfg.mic_enabled:
                _input_mode = "mixed"
            elif input_cfg.desktop_enabled:
                _input_mode = "desktop"
            else:
                _input_mode = "mic"
            start_msg = {
                "type": "start",
                "token": token,
                "transport": client_cfg.transport,
                "sample_rate": audio_cfg.sample_rate,
                "channels": audio_cfg.channels,
                "frame_ms": audio_cfg.frame_ms,
                "client_id": client_id,
                "input_mode": _input_mode,
            }
            await ws.send(json.dumps(start_msg))

            # Desktop capture legitimately sends zeros while nothing plays, and encoded
            # (opus) chunks can't be inspected, so only raw microphone PCM is checked.
            dead_input = (
                DeadInputDetector(str(input_cfg.mic_device or "default"))
                if _input_mode == "mic" and input_cfg.mode == "mic" and client_cfg.transport == "pcm"
                else None
            )
            async for chunk in audio_generator(proc):
                await ws.send(chunk)
                chunks_sent += 1
                if dead_input is not None:
                    notice = dead_input.observe(chunk)
                    if notice:
                        sys.stderr.write(notice + "\n")
                        sys.stderr.flush()
    except asyncio.CancelledError:
        pass
    except websockets.exceptions.ConnectionClosed as exc:
        code = getattr(exc, "code", None)
        reason = getattr(exc, "reason", "") or "connection closed"
        msg = f"stream ended: {reason}"
        if code is not None:
            msg += f" (code {code})"
        sys.stderr.write(msg + "\n")
    finally:
        stop_event.set()
        if captions_thread and captions_thread.is_alive():
            captions_thread.join(timeout=1.0)
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except Exception:
            proc.kill()
        if chunks_sent == 0:
            code = proc.poll()
            sys.stderr.write(
                f"warning: no audio chunks sent (capture exited early, ffmpeg code={code})\n"
            )
        if meter is not None:
            meter.join(timeout=0.5)
        if ffmpeg_stderr_thread.is_alive():
            ffmpeg_stderr_thread.join(timeout=0.5)
