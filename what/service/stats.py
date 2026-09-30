from __future__ import annotations

from dataclasses import dataclass
import time


@dataclass
class StatsSnapshot:
    samples: int
    avg_rtf: float
    avg_processing_ms: float
    avg_audio_ms: float
    last_update: float


class StatsTracker:
    def __init__(self, alpha: float = 0.2) -> None:
        self.alpha = alpha
        self.samples = 0
        self.avg_rtf = 0.0
        self.avg_processing_ms = 0.0
        self.avg_audio_ms = 0.0
        self.last_update = 0.0

    def update(self, processing_sec: float, audio_sec: float) -> None:
        if audio_sec <= 0:
            return
        rtf = processing_sec / audio_sec
        proc_ms = processing_sec * 1000.0
        audio_ms = audio_sec * 1000.0
        if self.samples == 0:
            self.avg_rtf = rtf
            self.avg_processing_ms = proc_ms
            self.avg_audio_ms = audio_ms
        else:
            self.avg_rtf = _ema(self.avg_rtf, rtf, self.alpha)
            self.avg_processing_ms = _ema(self.avg_processing_ms, proc_ms, self.alpha)
            self.avg_audio_ms = _ema(self.avg_audio_ms, audio_ms, self.alpha)
        self.samples += 1
        self.last_update = time.time()

    def snapshot(self) -> StatsSnapshot:
        return StatsSnapshot(
            samples=self.samples,
            avg_rtf=self.avg_rtf,
            avg_processing_ms=self.avg_processing_ms,
            avg_audio_ms=self.avg_audio_ms,
            last_update=self.last_update,
        )


def _ema(prev: float, value: float, alpha: float) -> float:
    return (alpha * value) + ((1.0 - alpha) * prev)
