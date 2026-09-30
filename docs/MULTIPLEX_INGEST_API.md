# Multiplexed Audio Ingest API (Draft)

This draft defines a transport-neutral payload for sending multiple named audio
streams into `what` for transcription.

## Goals

- Accept audio from multiple producers in one session.
- Preserve per-source identity (`source_id`) for downstream UX and correction logs.
- Keep ingest format simple: PCM frames + metadata.

## Non-Goals (v0.1)

- OS-level per-app capture parity across macOS/Linux/Windows.
- Automatic speaker diarization.
- Perfect sample-clock sync between unrelated producers.

## Envelope

Each message carries one frame chunk for one logical source.

```json
{
  "type": "audio_frame",
  "session_id": "sess_abc123",
  "stream_id": "stream_main",
  "source_id": "mic_main",
  "seq": 42,
  "ts_ms": 1771741530659,
  "format": {
    "codec": "pcm_s16le",
    "sample_rate_hz": 16000,
    "channels": 1
  },
  "duration_ms": 30,
  "data_b64": "BASE64_PCM_BYTES",
  "meta": {
    "source_kind": "mic",
    "speaker_id": "me",
    "app_id": "",
    "device_id": "avf:0"
  }
}
```

## Field Notes

- `session_id`: user/session scope in `what`.
- `stream_id`: producer stream instance (restart-safe identifier).
- `source_id`: stable logical source name (`mic_main`, `desktop_mix`, `discord_out`, etc.).
- `seq`: strictly monotonic per `stream_id`.
- `ts_ms`: producer timestamp (epoch ms).
- `format`: must remain stable per `stream_id`.
- `duration_ms`: expected frame duration (for jitter checks).
- `data_b64`: encoded PCM frame bytes.
- `meta`: optional routing hints and future diarization anchors.

## Control Messages

Open stream:

```json
{
  "type": "stream_open",
  "session_id": "sess_abc123",
  "stream_id": "stream_main",
  "source_id": "mic_main",
  "format": {
    "codec": "pcm_s16le",
    "sample_rate_hz": 16000,
    "channels": 1
  },
  "meta": {
    "source_kind": "mic",
    "speaker_id": "me"
  }
}
```

Close stream:

```json
{
  "type": "stream_close",
  "session_id": "sess_abc123",
  "stream_id": "stream_main",
  "source_id": "mic_main",
  "reason": "eof"
}
```

## JSON Schema (Draft 2020-12)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://what.local/schemas/multiplex_ingest_message.json",
  "type": "object",
  "required": ["type", "session_id", "stream_id", "source_id"],
  "properties": {
    "type": {
      "type": "string",
      "enum": ["stream_open", "audio_frame", "stream_close"]
    },
    "session_id": { "type": "string", "minLength": 1 },
    "stream_id": { "type": "string", "minLength": 1 },
    "source_id": { "type": "string", "minLength": 1 },
    "seq": { "type": "integer", "minimum": 0 },
    "ts_ms": { "type": "integer", "minimum": 0 },
    "duration_ms": { "type": "number", "exclusiveMinimum": 0 },
    "data_b64": { "type": "string", "contentEncoding": "base64" },
    "reason": { "type": "string" },
    "format": {
      "type": "object",
      "required": ["codec", "sample_rate_hz", "channels"],
      "properties": {
        "codec": { "type": "string", "enum": ["pcm_s16le"] },
        "sample_rate_hz": { "type": "integer", "enum": [8000, 16000, 24000, 32000, 44100, 48000] },
        "channels": { "type": "integer", "minimum": 1, "maximum": 8 }
      },
      "additionalProperties": false
    },
    "meta": {
      "type": "object",
      "properties": {
        "source_kind": { "type": "string", "enum": ["mic", "desktop", "app", "file", "other"] },
        "speaker_id": { "type": "string" },
        "app_id": { "type": "string" },
        "device_id": { "type": "string" }
      },
      "additionalProperties": true
    }
  },
  "allOf": [
    {
      "if": { "properties": { "type": { "const": "audio_frame" } } },
      "then": { "required": ["seq", "ts_ms", "format", "duration_ms", "data_b64"] }
    },
    {
      "if": { "properties": { "type": { "const": "stream_open" } } },
      "then": { "required": ["format"] }
    }
  ],
  "additionalProperties": false
}
```

## Recommended Processing Rules

- Reject out-of-order frames per `stream_id` (`seq` regression).
- Tolerate duplicates (`seq` repeat) by dropping duplicate frame.
- Buffer per-source independently.
- Allow optional mixed-down transcript + per-source transcript outputs.
- Emit transcript events with both:
  - `source_id` (for source attribution)
  - `speaker_id` (if provided by producer/UI)

## Versioning

- Add `schema_version` once first implementation lands.
- Keep backward compatibility for one minor version after changes.
