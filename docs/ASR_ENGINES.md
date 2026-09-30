# ASR engines

`what` keeps one public transcription schema irrespective of the inference
runtime. Ingest clients, SSE subscribers, captions, TTS and viseme consumers
must not branch on an engine name.

## Engine selection

`asr.engine` accepts `auto`, `faster_whisper`, `whisperkit`, and
`whisper_cpp`. `auto` selects WhisperKit on Apple Silicon and Faster-Whisper
elsewhere. A native worker path can be set through `asr.worker_path` or the
corresponding `WHAT_SERVICE_WORKER_PATH` environment variable.

## WhisperKit defaults (Apple Silicon)

The shared `[asr]` model/compute/device keys and the caption chunk size are tuned for
faster-whisper on the CUDA box. When the engine resolves to `whisperkit`, three of them
are replaced, because the CUDA values do not transfer:

| Setting | Shared default | WhisperKit | Why |
| --- | --- | --- | --- |
| model | `asr.model_size` (`medium`) | `asr.whisperkit_model_size` (`base`) | `medium` is not a validated Core ML model here; an interrupted conversion loads and then fails with "Error in reading the MIL network". |
| device | `asr.device` (`cuda`) | `auto` | `cuda` routed WhisperKit startup failures through the CUDA/CPU fallback and its prompt. |
| chunk | `audio.chunk_ms` (800, profiles may differ) | `audio.whisperkit_chunk_ms` (2500) | WhisperKit decodes whole utterances; short chunks cut words at boundaries. Captions therefore lag by about that chunk. |

Explicit choices still win: `--model`, `--device`, `--chunk-ms`, `WHAT_SERVICE_MODEL`,
`WHAT_SERVICE_DEVICE`. faster-whisper behaviour is unchanged.

The service verifies the engine with one decode at startup, then hands that loaded worker
to the first stream instead of loading the model again. A WhisperKit failure reports the
model and cache location rather than offering a CPU fallback (the usual cause is a bad
model cache, not missing hardware). The worker treats a model as cached only when every
Core ML component has its weights, and names the missing files otherwise.

Models are cached under `~/Library/Caches/what-whisperkit` (`WHAT_WHISPERKIT_DOWNLOAD_BASE`).
Removing a model's folder there makes it download again.

## Recognition context in events

Every segment event carries the recognizer that produced it, so corrections and any later
adaptation can be reproduced and reversed: `asr_engine`, `asr_model`, plus `session_id`,
`client_id`, `input_source_id`, `recording_epoch` and `recorded` (whether the audio is being
written to `<session>/<client_id>.wav`).

## Local worker protocol v1

Workers communicate over stdin/stdout as one JSON object per line. Every
request and response includes `version: 1` and a request `id`.

- `ready` checks that the model is loaded.
- `transcribe` carries base64 s16le PCM, sample rate, language and decoding
  preferences and returns normalized `text`, `segments`, and timing metadata.
- `shutdown` is best-effort cleanup.

Future partial messages may use `type: "partial"`; callers must retain the
request ID. The current pipeline emits its established chunk-final events, so
adding partial forwarding is a separate, non-breaking pipeline enhancement.

`whisper.cpp` must implement this same protocol. That preserves the option to
use a tuned Metal/quantized worker as a high-concurrency server backend without
changing any network API.

## Livestream acceptance test

Evaluate a 30–60 minute mixed-speech stream with TTS and viseme work enabled:

- p95 ASR real-time factor below 0.5;
- no unbounded ingest or inference queue growth;
- partial/final transcript events remain within the product latency budget;
- worker memory stabilizes after model warm-up;
- simulated worker death produces a useful service error and recoverable restart.
