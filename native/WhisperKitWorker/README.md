# what WhisperKit worker

This is the macOS-local ASR worker. It reads protocol-v1 JSON lines from stdin
and writes one matching response per request to stdout. The Python service owns
networking, VAD, backpressure, captions, TTS and viseme publication.

Build it on an Apple-silicon Mac:

```bash
cd native/WhisperKitWorker
swift build -c release
```

The Python service discovers the resulting executable automatically. Override
it with `WHAT_WHISPERKIT_WORKER=/absolute/path/to/what-whisperkit-worker`.

Rebuild after changing or pulling worker source or Swift package dependencies. The
Python adapter rejects an older bundled executable with the rebuild command.
Explicit custom worker paths remain the caller's responsibility.

The worker accepts a WhisperKit model identifier through `model_size` (or the
`asr.model_path` override, currently passed as a model identifier). Arbitrary local
model-directory selection is not established by this wrapper.

Models are cached under `~/Library/Caches/what-whisperkit`, overridable with
`WHAT_WHISPERKIT_DOWNLOAD_BASE`. When the selected compiled model is present, the
worker configures WhisperKit to load from disk with downloads disabled. The first
initialization of an uncached model may download and compile it. Packaging should
pre-provision the model and verify an offline startup.

If source changes appear to have no effect, rebuild the worker before debugging
model discovery. A successful `ready` response establishes model initialization;
a real audio decode is still required to verify Core ML execution. Restricted
sandboxes can allow initialization but deny IOSurface/GPU buffers during decode.
