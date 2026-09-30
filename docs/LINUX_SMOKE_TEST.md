# Linux desktop and replay smoke test

The Linux GUI uses FFmpeg's Pulse input and the default output's monitor source.
This works with a PulseAudio server or PipeWire's PulseAudio compatibility service;
it does not install or replace the session's audio server. FFmpeg and pactl must be
available. A pure ALSA session is not supported by this desktop path.

Close the previous GUI, then launch from this checkout:

```sh
.venv/bin/python -m what gui
```

The launcher supplies its Python interpreter to Electron to avoid accidentally using
another installation of `what`. An explicit WHAT_CLI override still takes precedence.
If the terminal says it is reusing an existing controller, ensure that controller
belongs to this checkout and version before interpreting the results.

1. Start Mic only and speak. Check the service terminal for `recording: client=...`
   with `enabled=True` and the absolute WAV path. Ctrl-click a word to replay it.
2. Enable Desktop and play speech through the default output. Confirm the Desktop
   panel receives it without a CoreAudio/LaunchAgent error.
3. Replay a transcript word while desktop capture runs. Replay must not reappear as
   new desktop speech. Use headphones to avoid acoustic feedback into the microphone.
4. Stop, start again, and close the app. Confirm capture stops and a new start works.
5. Try with an unavailable monitor/server. Startup should report a capture failure
   without crashing Electron or leaving a transcription client waiting for input.

Desktop capture resolves the output monitor at startup; restart capture after changing
system outputs. Live device migration/reconnect remains a separate validation item.

Automated checks cover PCM capture arguments, startup failures, child cleanup, replay
silencing, and WebSocket ingest producing a readable WAV with `recorded: true` metadata.
These checks do not establish live microphone/desktop or macOS acceptance.

The "service did not report a recording" message denotes absent recording metadata,
not a filesystem check. The Linux incident was traced to an old service from another
checkout still occupying port 8765. That version emitted no `recorded` field and
stored its WAVs under the other checkout. The GUI accepted its health response while
the newly launched service could not bind. Controller startup now rejects an occupied
service port with an actionable conflict error before spawning a service.

A fresh event should include `recorded`, `session_id`, and `client_id`; compare these
with the recording path printed by the service if replay still fails.

If CUDA preflight reports a missing library such as `libcublas.so.12`, a GUI-managed
service automatically retries on CPU. Its stdin is disconnected from the launch
terminal so it cannot wait on an invisible `[y/N]` prompt. This fallback does not
install CUDA libraries; CPU transcription may be slower. Direct interactive service
launches retain their existing confirmation prompt.

## NVIDIA startup setup

`what gui` checks for a usable NVIDIA GPU before launching the GUI. On Linux it first
tries the installed system/virtual-environment libraries. If required libraries are
missing, it installs `nvidia-cublas-cu12>=12,<13` and `nvidia-cudnn-cu12>=9,<10` into
its current virtual environment. First setup requires internet and can download over
1 GB; progress is printed in the launching terminal before the GUI readiness timer
starts. Later launches reuse the installed libraries. Concurrent setup attempts in
the same environment are serialized.

The service inherits the wheel library directories in `LD_LIBRARY_PATH`. Direct
`what service` startup performs the same preparation and restarts its Python process
when needed, because Linux's loader must see these paths at process startup.
Explicit CPU service launches and macOS skip this preparation. No system NVIDIA driver
is installed or changed. Outside a virtual environment the app reports what is missing
instead of modifying system Python. `WHAT_AUTO_INSTALL_CUDA=0` disables downloads while
retaining discovery of existing libraries. Setup failure is reported; the existing
CPU fallback remains available.

This follows the [faster-whisper Linux GPU instructions](https://github.com/SYSTRAN/faster-whisper#gpu)
for CTranslate2 4.5–4.x. Other CTranslate2 versions require manual setup.
Validated on this machine's RTX 3080 with a cached Whisper small model: actual decode
completed on `cuda` using `float16` after installing the runtime wheels.

## Comparing transcription context

The default `captions` profile now uses 2500 ms chunks on faster-whisper/Linux, matching
the WhisperKit/macOS chunk length (macOS reaches 2500 ms via the `whisperkit_chunk_ms`
override). Boundary selection can shorten either chunk. Linux uses `medium` by default;
macOS uses WhisperKit `base`. These are different engines and decoding configurations, so
model size alone does not establish accuracy.

The `captions_context` profile also uses 2500 ms chunks, so it is now equivalent to the
default and no longer a longer-context A/B. It is kept for experimentation: to compare
against shorter, lower-latency chunks, set a smaller `--chunk-ms` (or a custom profile) and
replay the same source material. Chunk length trades latency against context; it is not yet
an accuracy benchmark. macOS overrides remain unchanged.

Replay regression checks cover successive Ctrl-clicks even when an earlier browser
play request remains pending, Stop/end followed by replay, and edited-segment replay.
Each click uses a fresh recording URL so a growing WAV is not read through stale
cached metadata. Confirm these paths against live audio on both platforms.
