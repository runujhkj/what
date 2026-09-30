"""PCM ring writer for an external OBS program-audio mixer.

This deliberately uses the same RAUD v1 layout as scripts/obs_audio_feed.py.  The
desktop helper lives in the `what` environment, so it cannot import the root package;
keeping this tiny producer-side implementation here lets it tee captured PCM without
opening a second macOS capture device.
"""
from __future__ import annotations

import mmap
import struct
from pathlib import Path

MAGIC = 0x44554152  # 'RAUD'
VERSION = 1
HEADER = 64
WRITE_FRAMES_OFF = 32


class PcmFeedWriter:
    def __init__(self, path: str, sample_rate: int, channels: int,
                 ring_seconds: float = 6.0) -> None:
        self.path = Path(path)
        self.sample_rate = int(sample_rate)
        self.channels = int(channels)
        self.frame_bytes = self.channels * 2
        self.ring_bytes = int(self.sample_rate * ring_seconds) * self.frame_bytes
        self.write_frames = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        size = HEADER + self.ring_bytes
        with open(self.path, "wb") as fh:
            fh.truncate(size)
        self._fh = open(self.path, "r+b")
        self._mm = mmap.mmap(self._fh.fileno(), size)
        struct.pack_into("<IIIIII", self._mm, 0, MAGIC, VERSION, self.sample_rate,
                         self.channels, 0, self.ring_bytes)
        self._publish()

    def _publish(self) -> None:
        struct.pack_into("<Q", self._mm, WRITE_FRAMES_OFF, self.write_frames)

    def write(self, pcm: bytes) -> None:
        size = len(pcm) - (len(pcm) % self.frame_bytes)
        if size <= 0:
            return
        pos = (self.write_frames * self.frame_bytes) % self.ring_bytes
        first = min(size, self.ring_bytes - pos)
        self._mm[HEADER + pos:HEADER + pos + first] = pcm[:first]
        if size > first:
            self._mm[HEADER:HEADER + size - first] = pcm[first:size]
        self.write_frames += size // self.frame_bytes
        self._publish()

    def close(self) -> None:
        for obj in (getattr(self, "_mm", None), getattr(self, "_fh", None)):
            try:
                obj.close()
            except Exception:
                pass
