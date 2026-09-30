"""Versioned JSON-lines protocol shared by local native ASR workers.

The worker transport is intentionally independent of a model/runtime so a
WhisperKit process and a future whisper.cpp process are interchangeable.
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any

PROTOCOL_VERSION = 1


class WorkerProtocolError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkerRequest:
    request_id: str
    type: str
    payload: dict[str, Any]

    def line(self) -> bytes:
        return (json.dumps({"version": PROTOCOL_VERSION, "id": self.request_id, "type": self.type, **self.payload}) + "\n").encode()


def decode_pcm(payload: dict[str, Any]) -> bytes:
    return base64.b64decode(payload["pcm_s16le_b64"], validate=True)


def encode_pcm(pcm_bytes: bytes) -> str:
    return base64.b64encode(pcm_bytes).decode("ascii")


def parse_line(line: bytes) -> dict[str, Any]:
    try:
        message = json.loads(line)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkerProtocolError("worker emitted invalid JSON") from exc
    if message.get("version") != PROTOCOL_VERSION:
        raise WorkerProtocolError(f"unsupported worker protocol: {message.get('version')}")
    return message
