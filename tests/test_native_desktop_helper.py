import asyncio
import io
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from what.native_desktop_helper import (
    HelperState,
    _classify_capture_error,
    _local_capture_loop,
    _stream_loop,
    _start_coreaudio_tap_capture,
    _start_health_server,
    build_arg_parser,
    generate_test_pcm_frame,
)


def test_generate_test_pcm_frame_is_deterministic_and_sized():
    frame_samples = 160
    channels = 1
    a = generate_test_pcm_frame(
        frame_samples=frame_samples,
        sample_rate=16000,
        channels=channels,
        frequency_hz=440.0,
        amplitude=0.2,
        phase_offset=0,
    )
    b = generate_test_pcm_frame(
        frame_samples=frame_samples,
        sample_rate=16000,
        channels=channels,
        frequency_hz=440.0,
        amplitude=0.2,
        phase_offset=0,
    )
    assert a == b
    assert len(a) == frame_samples * channels * 2
    assert any(byte != 0 for byte in a)


def test_health_endpoint_reports_state():
    state = HelperState(started_at=time.time(), session_id="s1")
    state.stream_connected = True
    state.chunks_sent = 42
    state.retries = 1
    state.last_error = ""
    state.capture_mode = "ffmpeg-desktop"
    state.capture_state = "signal"
    state.permission_state = "granted"
    port = 28993
    server = _start_health_server(state=state, health_port=port)
    try:
        # small grace so the server thread starts
        time.sleep(0.05)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1.0) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        assert payload["ok"] is True
        assert payload["stream_connected"] is True
        assert payload["chunks_sent"] == 42
        assert payload["session_id"] == "s1"
        assert payload["capture_mode"] == "ffmpeg-desktop"
        assert payload["capture_state"] == "signal"
        assert payload["permission_state"] == "granted"
    finally:
        server.shutdown()
        server.server_close()


def test_capture_error_classification_permission():
    reason, perm = _classify_capture_error("Operation not permitted")
    assert reason == "permission_required"
    assert perm == "required"


def test_capture_error_classification_device_unavailable():
    reason, perm = _classify_capture_error("device not found")
    assert reason == "device_unavailable"
    assert perm == "granted"


def test_stream_loop_does_not_retry_screen_recording_denial(monkeypatch):
    """A denied TCC request must leave one quiet helper, not prompt in a loop."""
    state = HelperState(started_at=time.time(), capture_mode="native-capture")
    state.permission_state = "required"
    stop_event = threading.Event()

    async def _stop_soon():
        await asyncio.sleep(0.02)
        stop_event.set()

    async def _run():
        task = asyncio.create_task(_stop_soon())
        await _stream_loop(
            state=state,
            stop_event=stop_event,
            service_host="127.0.0.1",
            service_port=8765,
            ws_path="/ingest",
            pair_path="/pair",
            transport="pcm",
            capture_mode="native-capture",
            desktop_device="",
        )
        await task

    import types
    fake_websockets = types.SimpleNamespace()
    monkeypatch.setitem(sys.modules, "websockets", fake_websockets)
    monkeypatch.setattr("what.native_desktop_helper._pair_token", lambda *_args: (_ for _ in ()).throw(RuntimeError("denied")))
    asyncio.run(_run())
    assert state.capture_state == "permission_required"
    assert state.retries == 1


def test_arg_parser_accepts_native_capture_mode():
    parser = build_arg_parser()
    args = parser.parse_args(["--capture-mode", "native-capture"])
    assert args.capture_mode == "native-capture"


# --- Core Audio Tap gap tests (red until binary is wired in) ---


def test_start_coreaudio_tap_capture_command(monkeypatch):
    seen = {}

    class _DummyProc:
        stdout = subprocess.PIPE
        stderr = subprocess.PIPE

    def fake_popen(cmd, **kwargs):
        seen["cmd"] = list(cmd)
        return _DummyProc()

    monkeypatch.setattr("what.native_desktop_helper.subprocess.Popen", fake_popen)
    _start_coreaudio_tap_capture(sample_rate=16000, channels=1)
    assert "--sample-rate" in seen["cmd"]
    assert "16000" in seen["cmd"]
    assert "--channels" in seen["cmd"]
    assert "1" in seen["cmd"]


@pytest.mark.skipif(sys.platform != "darwin", reason="CoreAudio tap is macOS only")
def test_native_capture_mode_sets_core_audio_backend(monkeypatch):
    r_fd, w_fd = os.pipe()
    os.close(w_fd)

    class _FakeStdout:
        def fileno(self):
            return r_fd

    class _FakeProcForTap:
        stdout = _FakeStdout()
        stderr = io.BytesIO(b"")

        def terminate(self):
            pass

        def wait(self, timeout=None):
            pass

        def kill(self):
            pass

    monkeypatch.setattr(
        "what.native_desktop_helper._start_coreaudio_tap_capture",
        lambda **_: _FakeProcForTap(),
    )
    state = HelperState(started_at=0.0)
    stop = threading.Event()
    stop.set()
    try:
        asyncio.run(
            _local_capture_loop(
                state=state,
                stop_event=stop,
                capture_mode="native-capture",
                desktop_device="",
            )
        )
    finally:
        try:
            os.close(r_fd)
        except OSError:
            pass
    assert state.capture_backend == "core_audio_tap"


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
def test_coreaudio_tap_binary_test_tone_emits_pcm():
    binary = Path(__file__).parent.parent / "bin" / "what-coreaudio-tap"
    if not binary.exists():
        pytest.skip("binary not built")
    proc = subprocess.Popen(
        [str(binary), "--test-tone", "--sample-rate", "16000", "--channels", "1"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        chunk = proc.stdout.read(960)  # 30 ms of s16le mono at 16 kHz
        assert len(chunk) == 960
        assert any(b != 0 for b in chunk)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()
