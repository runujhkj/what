from __future__ import annotations

import os
import select
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Any

from .asr import AsrConfig
from .worker_protocol import WorkerProtocolError, WorkerRequest, encode_pcm, parse_line


def _check_bundled_build(worker: Path, package: Path) -> None:
    """A checkout update must not silently keep running an older native worker."""
    if not worker.is_file():
        return  # _start_worker supplies the missing-build diagnostic.
    inputs = [package / "Package.swift", package / "Package.resolved"]
    inputs.extend((package / "Sources").rglob("*.swift"))
    built_at = worker.stat().st_mtime_ns
    if any(path.is_file() and path.stat().st_mtime_ns > built_at for path in inputs):
        raise RuntimeError(
            "Bundled WhisperKit worker is older than its source. "
            "Run `swift build -c release` in native/WhisperKitWorker, then retry."
        )


class WhisperKitWorkerASR:
    """ASR adapter for the bundled local Swift WhisperKit worker."""

    def __init__(self, cfg: AsrConfig) -> None:
        self.cfg = cfg
        self._lock = threading.Lock()
        self._proc = self._start_worker()
        self._request("ready", {})

    def _worker_path(self) -> str:
        if self.cfg.worker_path:
            return self.cfg.worker_path
        if env_path := os.environ.get("WHAT_WHISPERKIT_WORKER"):
            return env_path
        root = Path(__file__).resolve().parents[1]
        package = root / "native" / "WhisperKitWorker"
        worker = package / ".build" / "release" / "what-whisperkit-worker"
        _check_bundled_build(worker, package)
        return str(worker)

    def _start_worker(self) -> subprocess.Popen[bytes]:
        path = self._worker_path()
        if not os.path.exists(path):
            raise RuntimeError(
                "WhisperKit worker is not built. Run `swift build -c release` in "
                "native/WhisperKitWorker, or set WHAT_WHISPERKIT_WORKER."
            )
        return subprocess.Popen(
            [path, "--model", self.cfg.model_path or self.cfg.model_size],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
        )

    def _request(self, request_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        # Transcription requests are idempotent. Recover once if a worker exits
        # before responding, which keeps a short-lived native crash from taking
        # down the network service.
        for attempt in range(2):
            request_id = uuid.uuid4().hex
            request = WorkerRequest(request_id, request_type, payload)
            with self._lock:
                if self._proc.poll() is not None:
                    if attempt:
                        raise RuntimeError("WhisperKit worker exited after restart")
                    self._proc = self._start_worker()
                if self._proc.stdin is None or self._proc.stdout is None:
                    raise RuntimeError("WhisperKit worker has no protocol pipes")
                self._proc.stdin.write(request.line())
                self._proc.stdin.flush()
                ready, _, _ = select.select(
                    [self._proc.stdout], [], [], max(0.1, self.cfg.worker_timeout_seconds)
                )
                line = self._proc.stdout.readline() if ready else b""
            if line:
                message = parse_line(line)
                if message.get("id") != request_id:
                    raise WorkerProtocolError("worker response ID did not match request")
                if message.get("type") == "error":
                    raise RuntimeError(message.get("message", "WhisperKit worker error"))
                return message
            if attempt:
                raise RuntimeError("WhisperKit worker timed out or closed its protocol stream")
            if self._proc.poll() is None:
                self._proc.terminate()
            self._proc = self._start_worker()
        raise AssertionError("unreachable")

    def transcribe(self, pcm_bytes: bytes) -> dict[str, Any]:
        message = self._request(
            "transcribe",
            {
                "pcm_s16le_b64": encode_pcm(pcm_bytes),
                "sample_rate": 16000,
                "language": self.cfg.language,
                "beam_size": self.cfg.beam_size,
                "word_timestamps": True,
                "condition_on_previous_text": self.cfg.condition_on_previous_text,
                # Live-tunable decode gates (rantbank "What ASR tuning" -> /control/asr
                # -> asr_cfg, read per-decode). WhisperKit's DecodingOptions honors these,
                # so edits take effect on the next chunk on the Metal backend too.
                "no_speech_threshold": self.cfg.no_speech_threshold,
                "logprob_threshold": self.cfg.logprob_threshold,
                "compression_ratio_threshold": self.cfg.compression_ratio_threshold,
            },
        )
        return message["result"]

    def close(self) -> None:
        if self._proc.poll() is None:
            try:
                self._request("shutdown", {})
            except Exception:
                pass
            self._proc.terminate()
