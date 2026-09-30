"""Future whisper.cpp worker adapter.

Only the process command differs from WhisperKit; protocol conformance is
shared and tested now so the performance worker never alters service APIs.
"""
from .whisperkit_worker import WhisperKitWorkerASR


class WhisperCppWorkerASR(WhisperKitWorkerASR):
    def _worker_path(self) -> str:
        import os

        path = self.cfg.worker_path or os.environ.get("WHAT_WHISPER_CPP_WORKER")
        if not path:
            raise RuntimeError(
                "whisper.cpp worker is not installed. Set asr.worker_path or "
                "WHAT_WHISPER_CPP_WORKER to a protocol-v1 worker executable."
            )
        return path
