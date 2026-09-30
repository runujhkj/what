from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import select
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass
from dataclasses import asdict
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .desktop_audio import build_desktop_input_args, normalize_desktop_backend
from .audio_feed import PcmFeedWriter


@dataclass
class HelperState:
    started_at: float
    stream_connected: bool = False
    chunks_sent: int = 0
    retries: int = 0
    last_error: str = ""
    last_connect_at: float = 0.0
    sample_rate: int = 16000
    channels: int = 1
    frame_ms: int = 30
    session_id: str = ""
    capture_mode: str = "tone"
    capture_backend: str = ""
    capture_state: str = "idle"
    permission_state: str = "unknown"
    last_rms: float = 0.0
    signal_frames: int = 0
    silent_frames: int = 0
    captured_frames: int = 0


def _pcm16_rms(frame: bytes) -> float:
    if not frame:
        return 0.0
    n = len(frame) // 2
    if n <= 0:
        return 0.0
    total = 0.0
    mv = memoryview(frame)
    for i in range(n):
        sample = int.from_bytes(mv[i * 2 : i * 2 + 2], byteorder="little", signed=True)
        total += float(sample) * float(sample)
    return math.sqrt(total / float(n))


def generate_test_pcm_frame(
    *,
    frame_samples: int,
    sample_rate: int,
    channels: int,
    frequency_hz: float = 440.0,
    amplitude: float = 0.20,
    phase_offset: int = 0,
) -> bytes:
    amp = max(0.0, min(1.0, float(amplitude)))
    out = bytearray()
    for i in range(frame_samples):
        t = (phase_offset + i) / float(sample_rate)
        sample = int(max(-1.0, min(1.0, math.sin(2.0 * math.pi * frequency_hz * t))) * amp * 32767.0)
        for _ in range(max(1, int(channels))):
            out += int(sample).to_bytes(2, byteorder="little", signed=True)
    return bytes(out)


def _pair_token(host: str, port: int, pair_path: str) -> str:
    url = f"http://{host}:{int(port)}{pair_path}"
    req = urllib.request.Request(url=url, method="POST")
    with urllib.request.urlopen(req, timeout=1.5) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    token = str(payload.get("token") or "")
    if not token:
        raise RuntimeError("pair endpoint did not return token")
    return token


def _classify_capture_error(text: str) -> tuple[str, str]:
    low = str(text or "").strip().lower()
    if not low:
        return ("capture_error", "unknown")
    if "operation not permitted" in low or "not authorized" in low or "permission denied" in low:
        return ("permission_required", "required")
    if "invalid data found" in low or "device not found" in low or "no such file or directory" in low:
        return ("device_unavailable", "granted")
    if "immediate exit requested" in low:
        return ("capture_stopped", "unknown")
    return ("capture_error", "unknown")


def _capture_error_message(text: str, permission_app: str = "") -> tuple[str, str]:
    reason, permission = _classify_capture_error(text)
    if permission == "required" and permission_app:
        # A parent app can own TCC responsibility even when this executable lives
        # inside WhatCoreAudioTap.app. Its hard-coded standalone advice is then wrong.
        return (f"permission_required: macOS denied desktop capture for {permission_app}. "
                "Its Screen Recording grant may refer to an older signed build; "
                "renew the parent app's grant and relaunch.", permission)
    return (f"{reason}: {text.strip()}", permission)


def _start_ffmpeg_desktop_capture(*, desktop_device: str, sample_rate: int, channels: int,
                                  backend: str | None = None) -> subprocess.Popen:
    """Capture desktop audio with ffmpeg via whichever backend this machine uses.

    The input args come from desktop_audio.build_desktop_input_args rather than being
    hardcoded to avfoundation, so the same bridge serves the macOS aggregate device and
    the Linux pulse monitor. That function raises ValueError with a human-readable
    reason when a backend can't run here; callers surface it as last_error.
    """
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        *build_desktop_input_args(backend or "auto", desktop_device),
        "-ac",
        str(channels),
        "-ar",
        str(sample_rate),
        "-f",
        "s16le",
        "-",
    ]
    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        bufsize=0,
    )


def _resolve_coreaudio_tap_binary() -> Path:
    env = os.environ.get("WHAT_COREAUDIO_TAP_HELPER", "")
    if env:
        return Path(env)
    base = Path(__file__).parent.parent / "bin"
    bare = base / "what-coreaudio-tap"
    if bare.exists():
        return bare
    # The tap is built as a .app bundle (WhatCoreAudioTap.app) -- use its executable when
    # the bare binary isn't present, so native-capture actually starts.
    app = base / "WhatCoreAudioTap.app" / "Contents" / "MacOS" / "WhatCoreAudioTap"
    if app.exists():
        return app
    return bare  # fall back (Popen errors clearly if neither exists)


def _start_coreaudio_tap_capture(*, sample_rate: int, channels: int) -> subprocess.Popen:
    binary = _resolve_coreaudio_tap_binary()
    cmd = [
        str(binary),
        "--sample-rate",
        str(sample_rate),
        "--channels",
        str(channels),
    ]
    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        bufsize=0,
    )


def screen_capture_permitted() -> bool:
    """Check TCC without opening a permission dialog or starting a capture."""
    import ctypes
    quartz = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    check = quartz.CGPreflightScreenCaptureAccess
    check.restype = ctypes.c_bool
    check.argtypes = []
    return bool(check())


def _publish_status(state: HelperState, path: str) -> None:
    if path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(".tmp")
        temp.write_text(json.dumps({**asdict(state), "updated_at": time.time()}))
        temp.replace(target)


class _HealthHandler(BaseHTTPRequestHandler):
    state_ref: HelperState | None = None

    def do_GET(self) -> None:  # noqa: N802 (http method naming)
        if self.path != "/health":
            self.send_response(404)
            self.end_headers()
            return
        state = self.state_ref
        if state is None:
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":false,"error":"no_state"}')
            return
        body = {
            "ok": True,
            "stream_connected": bool(state.stream_connected),
            "chunks_sent": int(state.chunks_sent),
            "retries": int(state.retries),
            "last_error": str(state.last_error or ""),
            "capture_mode": str(state.capture_mode or ""),
            "capture_backend": str(state.capture_backend or ""),
            "capture_state": str(state.capture_state or ""),
            "permission_state": str(state.permission_state or ""),
            "last_rms": float(state.last_rms or 0.0),
            "signal_frames": int(state.signal_frames or 0),
            "silent_frames": int(state.silent_frames or 0),
            "captured_frames": int(state.captured_frames or 0),
            "last_connect_at": float(state.last_connect_at or 0.0),
            "session_id": str(state.session_id or ""),
            "sample_rate": int(state.sample_rate),
            "channels": int(state.channels),
            "frame_ms": int(state.frame_ms),
            "uptime_sec": max(0.0, time.time() - float(state.started_at)),
        }
        payload = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return


def _start_health_server(*, state: HelperState, health_port: int) -> ThreadingHTTPServer:
    _HealthHandler.state_ref = state
    server = ThreadingHTTPServer(("127.0.0.1", int(health_port)), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


class StreamClock:
    """Decides when a capture has genuinely stalled, so silence may stand in for it.

    The ASR stream wants audio at real-time rate even when the capture delivers none (a
    suspended sink produces no frames at all), so the helper pads with silence. The old rule
    padded whenever one 30ms select() passed with no data -- but ffmpeg's PulseAudio input
    delivers in BURSTS, and the ordinary gap between bursts is longer than 30ms. Each gap got
    a fabricated silent frame, and then the real audio for that gap arrived and was sent too.
    Measured on a real session: 5,313 inserted 30ms silences at a steady 90ms rhythm, a
    recording 1.5x longer than the time that passed, and an audible 11 Hz chop in desktop
    replay and in the OBS recording.

    So padding is tied to wall-clock debt instead: silence is sent only when the stream has
    fallen more than `stall_s` behind real time, and only enough to catch it back up. The
    gap between bursts is far shorter than that, so real audio is never interleaved with
    invented silence.
    """

    def __init__(self, frame_s: float, stall_s: float = 0.25, now=time.monotonic) -> None:
        self.frame_s = float(frame_s)
        self.stall_s = max(float(stall_s), self.frame_s)
        self._now = now
        self._t0 = now()
        self._sent = 0

    def note_sent(self, frames: int = 1) -> None:
        self._sent += int(frames)

    def behind_s(self) -> float:
        return (self._now() - self._t0) - self._sent * self.frame_s

    def fill_frames(self) -> int:
        """Silent frames to send right now: zero unless genuinely stalled."""
        behind = self.behind_s()
        if behind <= self.stall_s:
            return 0
        return int(behind / self.frame_s)


async def _stream_loop(
    *,
    state: HelperState,
    stop_event: threading.Event,
    service_host: str,
    service_port: int,
    ws_path: str,
    pair_path: str,
    transport: str,
    capture_mode: str,
    desktop_device: str,
    desktop_backend: str = "auto",
    pause_file: str = "",
    program_feed: str = "",
    program_mute_file: str = "",
    permission_preflight: bool = False,
    permission_app: str = "",
) -> None:
    import websockets

    frame_samples = int(state.sample_rate * state.frame_ms / 1000)
    phase = 0
    frame_bytes = frame_samples * int(max(1, state.channels)) * 2
    native_capture_attempted = False
    while not stop_event.is_set():
        try:
            token = _pair_token(service_host, service_port, pair_path)
            ws_url = f"ws://{service_host}:{int(service_port)}{ws_path}"
            async with websockets.connect(ws_url, max_queue=None) as ws:
                await ws.send(
                    json.dumps(
                        {
                            "type": "start",
                            "token": token,
                            "transport": transport,
                            "sample_rate": int(state.sample_rate),
                            "channels": int(state.channels),
                            "frame_ms": int(state.frame_ms),
                            "client_id": f"desktop-helper-{state.session_id or 'session'}",
                            # Tag the stream so events carry input_source_id="desktop" -- lets
                            # the What OBS source (and any consumer) tell desktop from mic.
                            "input_mode": "desktop",
                        }
                    )
                )
                state.stream_connected = True
                state.last_connect_at = time.time()
                state.last_error = ""
                state.capture_mode = str(capture_mode)
                frame_interval = max(0.005, float(state.frame_ms) / 1000.0)
                if capture_mode == "tone":
                    state.capture_backend = "synthetic_tone"
                    state.capture_state = "signal"
                    state.permission_state = "granted"
                    while not stop_event.is_set():
                        frame = generate_test_pcm_frame(
                            frame_samples=frame_samples,
                            sample_rate=state.sample_rate,
                            channels=state.channels,
                            phase_offset=phase,
                        )
                        phase += frame_samples
                        await ws.send(frame)
                        state.chunks_sent += 1
                        await asyncio.sleep(frame_interval)
                elif capture_mode in {"ffmpeg-desktop", "native-capture"}:
                    state.capture_state = "starting"
                    # Only the CoreAudio tap is macOS-only. ffmpeg-desktop is portable:
                    # its input args come from the platform's desktop backend, which
                    # raises with a reason when it can't run here.
                    if capture_mode == "native-capture" and sys.platform != "darwin":
                        state.capture_state = "failed"
                        state.permission_state = "unknown"
                        raise RuntimeError("native-capture (CoreAudio tap) mode is macOS-only")
                    if capture_mode == "native-capture":
                        if permission_preflight and not screen_capture_permitted():
                            state.permission_state = "required"
                            raise RuntimeError("Screen Recording permission required. Enable Rantology in "
                                               "System Settings, then quit and relaunch the app.")
                        state.capture_backend = "core_audio_tap"
                        native_capture_attempted = True
                        proc = _start_coreaudio_tap_capture(
                            sample_rate=state.sample_rate,
                            channels=state.channels,
                        )
                    else:
                        _backend = normalize_desktop_backend(desktop_backend)
                        state.capture_backend = f"ffmpeg_{_backend}_bridge"
                        try:
                            proc = _start_ffmpeg_desktop_capture(
                                desktop_device=str(desktop_device or ""),
                                sample_rate=state.sample_rate,
                                channels=state.channels,
                                backend=_backend,
                            )
                        except ValueError as exc:
                            state.capture_state = "failed"
                            state.permission_state = "unknown"
                            raise RuntimeError(str(exc)) from exc
                    assert proc.stdout is not None
                    assert proc.stderr is not None
                    stdout_fd = proc.stdout.fileno()
                    silence_frame = b"\x00" * int(frame_bytes)
                    pause_path = Path(pause_file) if pause_file else None
                    program_mute_path = Path(program_mute_file) if program_mute_file else None
                    feed_writer = (PcmFeedWriter(program_feed, state.sample_rate, state.channels)
                                   if program_feed else None)
                    pcm_buf = bytearray()
                    signal_rms_min = float(
                        str(os.environ.get("WHAT_DESKTOP_NATIVE_HELPER_SIGNAL_RMS_MIN", "12") or "12")
                    )
                    stall_s = float(
                        str(os.environ.get("WHAT_DESKTOP_NATIVE_HELPER_STALL_FILL_S", "0.25") or "0.25")
                    )
                    clock = StreamClock(frame_interval, stall_s)
                    try:
                        state.capture_state = "starting"
                        state.permission_state = "granted"
                        while not stop_event.is_set():
                            # send() may complete without yielding when the socket has
                            # room. Blocking select here then starves ping/pong handling
                            # indefinitely, even while PCM keeps flowing. Poll off-loop
                            # so transport keepalives and shutdown always get scheduled.
                            ready, _, _ = await asyncio.to_thread(
                                select.select, [stdout_fd], [], [], frame_interval)
                            if not ready:
                                state.last_rms = 0.0
                                state.capture_state = "silent"
                                # Usually just the gap between capture bursts: the audio for
                                # it is already on its way. Pad only a real stall.
                                for _ in range(clock.fill_frames()):
                                    await ws.send(silence_frame)
                                    clock.note_sent()
                                    state.silent_frames += 1
                                    state.chunks_sent += 1
                                continue
                            chunk = os.read(stdout_fd, frame_bytes * 4)
                            if not chunk:
                                err = proc.stderr.read().decode("utf-8", errors="replace")
                                reason, perm = _capture_error_message(err, permission_app)
                                state.capture_state = "failed"
                                state.permission_state = perm
                                raise RuntimeError(reason)
                            pcm_buf.extend(chunk)
                            sent_any = False
                            while len(pcm_buf) >= frame_bytes:
                                frame = bytes(pcm_buf[:frame_bytes])
                                del pcm_buf[:frame_bytes]
                                state.captured_frames += 1
                                # During a review replay the UI injects the selected WAV
                                # directly into the program mixer. Keep capture alive (so
                                # TCC is not re-entered), but omit its copy of that playback
                                # from the raw desktop program lane.
                                if feed_writer is not None and not (
                                    program_mute_path is not None and program_mute_path.exists()
                                ):
                                    feed_writer.write(frame)
                                # Keep the ScreenCaptureKit stream alive during review
                                # playback. Restarting it re-enters TCC and can re-show
                                # the permission banner even after a grant. Silence the
                                # ASR lane instead; the operator still hears playback on
                                # the normal desktop output.
                                if pause_path is not None and pause_path.exists():
                                    state.capture_state = "suppressed"
                                    await ws.send(silence_frame)
                                    clock.note_sent()
                                    state.silent_frames += 1
                                    state.chunks_sent += 1
                                    continue
                                rms = _pcm16_rms(frame)
                                state.last_rms = float(rms)
                                # ACTUAL silence gate: below the signal floor, send a zero
                                # frame instead of the quiet audio. Zeros make the service
                                # VAD reliably reject -> the desktop ASR worker doesn't decode
                                # when nothing is really playing, so it stops burning GPU the
                                # mic worker needs (previously every captured frame was sent
                                # and only the service VAD gated, letting ambient/quiet through).
                                if rms >= signal_rms_min:
                                    await ws.send(frame)
                                    state.signal_frames += 1
                                else:
                                    await ws.send(silence_frame)
                                    state.silent_frames += 1
                                clock.note_sent()
                                state.chunks_sent += 1
                                sent_any = True
                            if sent_any:
                                if state.last_rms >= signal_rms_min:
                                    state.capture_state = "signal"
                                else:
                                    state.capture_state = "silent"
                    finally:
                        if feed_writer is not None:
                            feed_writer.close()
                        try:
                            proc.terminate()
                        except Exception:
                            pass
                        try:
                            proc.wait(timeout=0.5)
                        except Exception:
                            try:
                                proc.kill()
                            except Exception:
                                pass
                else:
                    state.capture_state = "failed"
                    state.permission_state = "unknown"
                    raise RuntimeError(f"unsupported capture mode: {capture_mode}")
        except Exception as exc:
            state.stream_connected = False
            state.retries += 1
            state.last_error = str(exc)
            print(f"[desktop] capture failed: {exc}", file=sys.stderr, flush=True)
            # A ScreenCaptureKit denial is not a transient capture failure. Retrying
            # it immediately reopens macOS's Screen Recording dialog every 500 ms,
            # which leaves the user unable to respond. Keep the owned helper alive
            # in a clear stopped state instead, so its supervisor cannot respawn it;
            # closing the app sends SIGTERM. Also park unclassified native failures:
            # a connection/capture error must not repeatedly recreate SCStream (and
            # its permission dialog). Pairing failures before capture may still retry.
            if state.permission_state == "required" or native_capture_attempted:
                state.capture_state = ("permission_required" if state.permission_state == "required"
                                       else "failed")
                while not stop_event.is_set():
                    await asyncio.sleep(0.1)
                return
            if state.capture_state != "failed":
                state.capture_state = "retrying"
            await asyncio.sleep(0.5)


async def _local_capture_loop(
    *,
    state: HelperState,
    stop_event: threading.Event,
    capture_mode: str,
    desktop_device: str,
    desktop_backend: str = "auto",
) -> None:
    frame_samples = int(state.sample_rate * state.frame_ms / 1000)
    frame_bytes = frame_samples * int(max(1, state.channels)) * 2
    frame_interval = max(0.005, float(state.frame_ms) / 1000.0)
    phase = 0
    signal_rms_min = float(
        str(os.environ.get("WHAT_DESKTOP_NATIVE_HELPER_SIGNAL_RMS_MIN", "12") or "12")
    )
    state.stream_connected = False
    state.last_error = ""
    state.capture_mode = str(capture_mode or "native-capture")
    if capture_mode == "tone":
        state.capture_backend = "synthetic_tone"
        state.permission_state = "granted"
        while not stop_event.is_set():
            frame = generate_test_pcm_frame(
                frame_samples=frame_samples,
                sample_rate=state.sample_rate,
                channels=state.channels,
                phase_offset=phase,
            )
            phase += frame_samples
            rms = _pcm16_rms(frame)
            state.last_rms = float(rms)
            state.captured_frames += 1
            if rms >= signal_rms_min:
                state.signal_frames += 1
                state.capture_state = "signal"
            else:
                state.silent_frames += 1
                state.capture_state = "silent"
            await asyncio.sleep(frame_interval)
        return
    if capture_mode not in {"ffmpeg-desktop", "native-capture"}:
        state.capture_state = "failed"
        state.permission_state = "unknown"
        state.last_error = f"unsupported capture mode: {capture_mode}"
        while not stop_event.is_set():
            await asyncio.sleep(0.1)
        return
    # Only the CoreAudio tap is macOS-only; ffmpeg-desktop follows the platform backend.
    if capture_mode == "native-capture" and sys.platform != "darwin":
        state.capture_state = "failed"
        state.permission_state = "unknown"
        state.last_error = "native-capture (CoreAudio tap) mode is macOS-only"
        while not stop_event.is_set():
            await asyncio.sleep(0.1)
        return
    if capture_mode == "native-capture":
        state.capture_backend = "core_audio_tap"
        proc = _start_coreaudio_tap_capture(
            sample_rate=state.sample_rate,
            channels=state.channels,
        )
    else:
        _backend = normalize_desktop_backend(desktop_backend)
        state.capture_backend = f"ffmpeg_{_backend}_bridge"
        try:
            proc = _start_ffmpeg_desktop_capture(
                desktop_device=str(desktop_device or ""),
                sample_rate=state.sample_rate,
                channels=state.channels,
                backend=_backend,
            )
        except ValueError as exc:
            # The backend said why (no pactl, nothing playing, unimplemented). That
            # message is the one worth showing, so keep it verbatim.
            state.capture_state = "failed"
            state.permission_state = "unknown"
            state.last_error = str(exc)
            while not stop_event.is_set():
                await asyncio.sleep(0.1)
            return
    assert proc.stdout is not None
    assert proc.stderr is not None
    stdout_fd = proc.stdout.fileno()
    pcm_buf = bytearray()
    try:
        state.capture_state = "starting"
        state.permission_state = "granted"
        while not stop_event.is_set():
            ready, _, _ = select.select([stdout_fd], [], [], frame_interval)
            if not ready:
                state.last_rms = 0.0
                state.capture_state = "silent"
                state.silent_frames += 1
                continue
            chunk = os.read(stdout_fd, frame_bytes * 4)
            if not chunk:
                err = proc.stderr.read().decode("utf-8", errors="replace")
                reason, perm = _classify_capture_error(err)
                state.capture_state = "failed"
                state.permission_state = perm
                state.last_error = reason
                break
            pcm_buf.extend(chunk)
            sent_any = False
            while len(pcm_buf) >= frame_bytes:
                frame = bytes(pcm_buf[:frame_bytes])
                del pcm_buf[:frame_bytes]
                rms = _pcm16_rms(frame)
                state.last_rms = float(rms)
                state.captured_frames += 1
                if rms >= signal_rms_min:
                    state.signal_frames += 1
                else:
                    state.silent_frames += 1
                sent_any = True
            if sent_any:
                if state.last_rms >= signal_rms_min:
                    state.capture_state = "signal"
                else:
                    state.capture_state = "silent"
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=0.5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-id", default="")
    parser.add_argument("--service-host", default="127.0.0.1")
    parser.add_argument("--service-port", type=int, default=8765)
    parser.add_argument("--ws-path", default="/ingest")
    parser.add_argument("--pair-path", default="/pair")
    parser.add_argument("--transport", default="pcm", choices=["pcm"])
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--channels", type=int, default=1)
    parser.add_argument("--frame-ms", type=int, default=30)
    parser.add_argument("--health-port", type=int, default=8793)
    parser.add_argument(
        "--capture-mode",
        default=str(os.environ.get("WHAT_DESKTOP_NATIVE_HELPER_CAPTURE_MODE", "tone")),
        choices=["tone", "ffmpeg-desktop", "native-capture"],
    )
    parser.add_argument(
        "--desktop-device",
        default=str(os.environ.get("WHAT_DESKTOP_NATIVE_HELPER_DEVICE", "")),
    )
    parser.add_argument(
        # "auto" resolves per platform (avfoundation / pulse / wasapi) at capture time.
        "--desktop-backend",
        default=str(os.environ.get("WHAT_DESKTOP_NATIVE_HELPER_BACKEND", "auto")),
    )
    parser.add_argument("--no-stream", action="store_true")
    parser.add_argument("--pause-file", default="",
                        help="while this file exists, send silence without restarting capture")
    parser.add_argument("--program-feed", default="",
                        help="tee raw desktop PCM to this ring for the OBS program mixer")
    parser.add_argument("--program-mute-file", default="",
                        help="while this file exists, keep capture out of the program feed")
    parser.add_argument("--permission-preflight", action="store_true",
                        help="require an existing macOS screen grant; never open a permission dialog")
    parser.add_argument("--status-file", default="", help="publish capture state and errors as JSON")
    parser.add_argument("--permission-app", default="",
                        help="parent app that owns capture permission, for accurate error guidance")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    stop_event = threading.Event()

    def _handle_signal(_signum, _frame) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    state = HelperState(
        started_at=time.time(),
        sample_rate=int(args.sample_rate),
        channels=int(args.channels),
        frame_ms=int(args.frame_ms),
        session_id=str(args.session_id or ""),
        capture_mode=str(args.capture_mode or "tone"),
    )
    server = _start_health_server(state=state, health_port=int(args.health_port))
    def publish_status():
        while not stop_event.is_set():
            try:
                _publish_status(state, args.status_file)
            except OSError as exc:
                print(f"[desktop] status write failed: {exc}", file=sys.stderr, flush=True)
            stop_event.wait(0.5)
    status_thread = threading.Thread(target=publish_status, daemon=True)
    status_thread.start()
    try:
        if args.no_stream:
            asyncio.run(
                _local_capture_loop(
                    state=state,
                    stop_event=stop_event,
                    capture_mode=str(args.capture_mode),
                    desktop_device=str(args.desktop_device or ""),
                    desktop_backend=str(args.desktop_backend or "auto"),
                )
            )
            return 0
        asyncio.run(
            _stream_loop(
                state=state,
                stop_event=stop_event,
                service_host=str(args.service_host),
                service_port=int(args.service_port),
                ws_path=str(args.ws_path),
                pair_path=str(args.pair_path),
                transport=str(args.transport),
                capture_mode=str(args.capture_mode),
                desktop_device=str(args.desktop_device or ""),
                desktop_backend=str(args.desktop_backend or "auto"),
                pause_file=str(args.pause_file or ""),
                program_feed=str(args.program_feed or ""),
                program_mute_file=str(args.program_mute_file or ""),
                permission_preflight=bool(args.permission_preflight),
                permission_app=str(args.permission_app),
            )
        )
        return 0
    finally:
        stop_event.set()
        status_thread.join(timeout=1)
        state.stream_connected = False
        if state.capture_state not in {"permission_required", "failed"}:
            state.capture_state = "stopped"
        try:
            _publish_status(state, args.status_file)
        except OSError:
            pass
        try:
            server.shutdown()
        except Exception:
            pass
        try:
            server.server_close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
