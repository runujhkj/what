# Core Audio Tap Migration

Replaces the BlackHole loopback device + ffmpeg AVFoundation bridge (`ffmpeg-desktop` capture mode) with Apple's native Core Audio Taps API (`CATapDescription` / `AudioHardwareCreateProcessTap`, macOS 14.2+). No driver installation, no output re-routing, no virtual audio device.

---

## How `bin/what-coreaudio-tap` works on macOS 26 (Tahoe)

**`bin/what-coreaudio-tap` is a shell script**, not a compiled binary. It calls:

```bash
exec swift "$SCRIPT_DIR/what-coreaudio-tap.swift" "$@"
```

The Swift code lives in `bin/what-coreaudio-tap.swift`.

### Why a script instead of a compiled binary

macOS 26 (Tahoe) introduced a policy that kills ad-hoc-signed standalone binaries at exec time if they link against audio frameworks (`AVFAudio`, `CoreAudio`). This applies regardless of entitlements or hardened runtime flags, and also applies to self-signed certificate signatures (only Apple Developer certs with a Team ID are accepted).

Running via the `swift` interpreter sidesteps this entirely: the running process is `/usr/bin/swift`, which is Apple-signed and trusted. Audio API calls succeed under Swift's identity.

### TCC permissions

On first run, macOS will show a **Screen Recording** permission dialog for your terminal emulator (Terminal.app, iTerm2, etc.), not for `what-coreaudio-tap` itself. Grant it once. The permission is tied to the terminal app and survives indefinitely — no re-prompting after code changes.

### Startup time

`swift` compiles the script on first run and caches the result. First invocation: ~3–10 seconds. Subsequent invocations: nearly instant. For a long-running capture session this overhead is negligible.

### Apple Developer account (optional)

If you later get an Apple Developer account, `native/what-coreaudio-tap/build.sh` can produce a compiled binary signed with hardened runtime + entitlements. Set `WHAT_SIGNING_IDENTITY` to your Developer cert and update `_resolve_coreaudio_tap_binary()` in `native_desktop_helper.py` to point at the compiled binary. The script approach remains the default.

---

## Binary interface: `bin/what-coreaudio-tap`

The binary is a standalone Swift executable. It is spawned as a subprocess by `_start_coreaudio_tap_capture()` in `what/native_desktop_helper.py`, replacing the existing `_start_ffmpeg_desktop_capture()` call.

### Invocation

```
bin/what-coreaudio-tap [options]

  --sample-rate INT     PCM output sample rate (default: 16000)
  --channels INT        PCM output channels (default: 1)
  --frame-ms INT        Advisory frame size in ms; binary may use internally (default: 30)
  --test-tone           Emit synthetic 440 Hz sine instead of system audio (no permission needed)
```

### Output contract

| Stream | Content |
|--------|---------|
| stdout | s16le PCM, continuous, at `--sample-rate` / `--channels`. No header. |
| stderr | Human-readable error on failure. Text must be compatible with `_classify_capture_error()`. |
| exit 0 | Clean shutdown after SIGTERM. |
| exit 1 | Permission denied — stderr must contain "Operation not permitted" or "not authorized". |
| exit 2 | Device unavailable — stderr must contain "device not found". |
| exit 3 | Other runtime error. |

`_classify_capture_error()` in `what/native_desktop_helper.py` already handles these exact strings; the binary just needs to emit them.

### macOS version guard

Binary checks `ProcessInfo.processInfo.operatingSystemVersion` at startup and exits 3 with "macOS 14.2 or later required" if the host is older. The Python caller handles this via the existing `_classify_capture_error` fallthrough → `"capture_error"`.

---

## Swift implementation sketch

```swift
// macOS 14.2+ required
import CoreAudio
import Foundation

// 1. Create a system-wide tap description
let tapDesc = CATapDescription(stereoMixdownOfProcesses: [])
// stereoMixdownOfProcesses([]) = tap all processes (system mix)

// 2. Create the tap
var tapID: AudioObjectID = kAudioObjectUnknown
let err = AudioHardwareCreateProcessTap(tapDesc, &tapID)
guard err == noErr else {
    fputs("Operation not permitted\n", stderr)
    exit(1)
}

// 3. Create an aggregate device that wraps the tap
//    (or use AVAudioEngine with the tap as input node)

// 4. Pull PCM frames from the tap, write s16le to stdout.
```

Reference implementations:
- https://github.com/insidegui/AudioCap (Swift, macOS 14.4+, uses CATapDescription)
- https://github.com/makeusabrew/audiotee (C, minimal)
- https://gist.github.com/sudara/34f00efad69a7e8ceafa078ea0f76f6f (macOS 14.2 minimal)

The binary does not need to handle routing, device selection, or driver installation — those layers are removed entirely once the binary is wired in.

---

## Python integration: `what/native_desktop_helper.py`

### New function

```python
def _start_coreaudio_tap_capture(*, sample_rate: int, channels: int) -> subprocess.Popen:
    binary = _resolve_coreaudio_tap_binary()
    cmd = [
        str(binary),
        "--sample-rate", str(sample_rate),
        "--channels", str(channels),
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
    return Path(__file__).parent.parent / "bin" / "what-coreaudio-tap"
```

### Wiring change in `_stream_loop` and `_local_capture_loop`

Current code in the `native-capture` branch:
```python
# Transitional bridge: native-capture mode keeps the API
# stable while desktop ingest migrates off legacy routing.
state.capture_backend = "ffmpeg_avfoundation_bridge"
...
proc = _start_ffmpeg_desktop_capture(...)
```

Replace with:
```python
state.capture_backend = "core_audio_tap"
state.capture_state = "starting"
proc = _start_coreaudio_tap_capture(
    sample_rate=state.sample_rate,
    channels=state.channels,
)
```

The rest of the read/send loop (`select` → `os.read` → `ws.send`) is unchanged — it already handles a generic PCM subprocess pipe.

The `desktop_device` argument is not passed to the tap binary (system-mix tap has no device selector). The `if not str(desktop_device or "").strip()` guard that currently gates the ffmpeg path is removed for `native-capture`.

---

## Test pre-pass

### Existing tests that apply to the new binary

| Test | File | Coverage |
|------|------|----------|
| `test_capture_error_classification_permission` | `test_native_desktop_helper.py` | Binary's exit 1 stderr → `permission_required`. Already passes. |
| `test_capture_error_classification_device_unavailable` | `test_native_desktop_helper.py` | Binary's exit 2 stderr → `device_unavailable`. Already passes. |
| `test_arg_parser_accepts_native_capture_mode` | `test_native_desktop_helper.py` | `native-capture` arg slot that the binary fills. Already passes. |
| `test_health_endpoint_reports_state` | `test_native_desktop_helper.py` | Health endpoint still works; `capture_mode` / `capture_state` fields apply unchanged. Already passes. |
| `test_native_desktop_helper_start_defaults_to_native_capture_mode` | `test_controller_desktop_audio_api.py` | Controller defaults to `native-capture` mode — this is what drives the binary. Already passes. |
| `test_native_desktop_helper_start_stop_endpoints` | `test_controller_desktop_audio_api.py` | Start/stop lifecycle through controller. Already passes. |

These six tests will remain green through the swap and do not need to be modified.

### Gaps — tests to add in `tests/test_native_desktop_helper.py`

**1. Command construction unit test (no subprocess spawn)**

```python
def test_start_coreaudio_tap_capture_command(monkeypatch):
    seen = {}
    def fake_popen(cmd, **kwargs):
        seen["cmd"] = cmd
        return DummyProc()
    monkeypatch.setattr("what.native_desktop_helper.subprocess.Popen", fake_popen)
    _start_coreaudio_tap_capture(sample_rate=16000, channels=1)
    assert "--sample-rate" in seen["cmd"]
    assert "16000" in seen["cmd"]
    assert "--channels" in seen["cmd"]
    assert "1" in seen["cmd"]
```

**2. `native-capture` mode sets `core_audio_tap` backend on state (no real subprocess)**

```python
import asyncio, threading

def test_native_capture_mode_sets_core_audio_backend(monkeypatch):
    # Fake subprocess that emits 1 frame of silence then closes stdout
    frame = b"\x00" * 960  # 16000 Hz * 1ch * 2 bytes * 30ms
    class FakeProc:
        stdout = io.BytesIO(frame)
        stderr = io.BytesIO(b"")
        def terminate(self): pass
        def wait(self, timeout=None): pass
        def kill(self): pass
    monkeypatch.setattr(
        "what.native_desktop_helper._start_coreaudio_tap_capture",
        lambda **_: FakeProc(),
    )
    state = HelperState(started_at=0.0)
    stop = threading.Event()
    stop.set()  # exits after first frame
    asyncio.run(_local_capture_loop(
        state=state, stop_event=stop,
        capture_mode="native-capture", desktop_device="",
    ))
    assert state.capture_backend == "core_audio_tap"
```

**3. Binary smoke test (macOS only, requires binary built)**

```python
import sys, subprocess, pytest

@pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
def test_coreaudio_tap_binary_tone_mode_emits_pcm(tmp_path):
    binary = Path(__file__).parent.parent / "bin" / "what-coreaudio-tap"
    if not binary.exists():
        pytest.skip("binary not built")
    proc = subprocess.Popen(
        [str(binary), "--test-tone", "--sample-rate", "16000", "--channels", "1"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        chunk = proc.stdout.read(960)  # 30ms of s16le
        assert len(chunk) == 960
        assert any(b != 0 for b in chunk)  # non-silent
    finally:
        proc.terminate()
        proc.wait(timeout=1)
```

### Tests NOT needed

- `test_desktop_audio_manager.py` — covers BlackHole install/uninstall; deleted in Stage 7, not modified here.
- `test_audio_routing_manager.py` — covers SwitchAudioSource routing; deleted in Stage 7, not modified here.
- `test_desktop_capture_state_machine.py` — covers probe fallback logic that is removed once native path is default; no change needed for Stage 4.

---

## What does NOT change in this step

- The WebSocket PCM streaming loop (`_stream_loop`) — only the subprocess call changes.
- The `_local_capture_loop` (`--no-stream` path) — same.
- Health server and all `HelperState` fields — unchanged.
- `_classify_capture_error` — no changes needed; binary stderr matches existing patterns.
- Controller API endpoints — no changes needed.
- `native_desktop_helper_manager.py` — no changes needed.
- Audio routing manager, desktop audio manager — untouched until Stage 7 removal.
