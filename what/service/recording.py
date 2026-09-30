"""Session audio recording for review / replay / the self-improvement corpus.

The frames handed to the pipeline are always 16-bit PCM (regardless of pcm/opus
transport), and the pipeline derives segment timestamps from sample counts starting at
the first frame -- so teeing those frames to a WAV whose sample 0 is the first frame gives
a recording whose offsets line up exactly with segment/word abs_start seconds. That
alignment is what makes click-a-word-to-replay and (audio-slice, corrected-text) training
pairs possible.

Recording is on by default; set WHAT_RECORD_AUDIO=0 to disable.
"""

from __future__ import annotations

import os
import struct
import sys
from typing import Iterable, Iterator


def recording_enabled() -> bool:
    return os.environ.get("WHAT_RECORD_AUDIO", "1") not in ("0", "false", "False", "")


def _wav_header(data_len: int, sample_rate: int, channels: int, sampwidth: int = 2) -> bytes:
    """Canonical 44-byte PCM WAV header for the given data length."""
    byte_rate = sample_rate * channels * sampwidth
    block_align = channels * sampwidth
    return (
        b"RIFF"
        + struct.pack("<I", 36 + data_len)
        + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, channels, sample_rate, byte_rate, block_align, sampwidth * 8)
        + b"data"
        + struct.pack("<I", data_len)
    )


def recording_duration_sec(wav_path: str, sample_rate: int, channels: int) -> float:
    """Return durable audio duration for an open or finalized PCM recording.

    The service appends a new connection to the same per-client WAV. The file size is
    authoritative while a writer has the file open, because an older process may not
    yet have published the header length.
    """
    try:
        data_bytes = max(0, os.path.getsize(wav_path) - 44)
        return data_bytes / float(max(1, sample_rate * channels * 2))
    except OSError:
        return 0.0


def tee_frames_to_wav(
    frames: Iterable[bytes], wav_path: str, sample_rate: int, channels: int
) -> Iterator[bytes]:
    """Yield each PCM frame unchanged while APPENDING it to a WAV at wav_path.

    Append-safe: a reconnect within a session must not truncate the audio already
    recorded (the old wave.open('wb') wiped it, so a flaky desktop capture left only
    the last fragment). We keep raw PCM after a placeholder header and rewrite the
    header sizes on close; if the process dies before close, the header stays a
    placeholder but the file-size-based duration reader still recovers the length.
    Publish the header periodically while recording too: review playback slices with
    ffmpeg, which trusts the WAV header rather than the file size and otherwise sees
    an open recording as zero seconds long. A failure to open/write never interrupts
    the transcription stream.
    """
    fh = None
    sampwidth = 2  # s16le
    written = 0
    header_publish_at = 0

    def _publish_header() -> None:
        """Make an in-progress WAV immediately readable by normal decoders."""
        nonlocal header_publish_at
        if fh is None:
            return
        try:
            fh.seek(0)
            fh.write(_wav_header(max(0, written), sample_rate, channels, sampwidth))
            fh.seek(0, os.SEEK_END)
            fh.flush()
            # Publish no more often than about once a second of audio, rather than
            # seeking/flushing once per 30 ms capture frame.
            header_publish_at = written + sample_rate * channels * sampwidth
        except Exception:
            pass
    try:
        os.makedirs(os.path.dirname(wav_path) or ".", exist_ok=True)
        existing = os.path.exists(wav_path) and os.path.getsize(wav_path) >= 44
        fh = open(wav_path, "r+b" if existing else "w+b")
        if existing:
            fh.seek(0, os.SEEK_END)
            written = fh.tell() - 44
        else:
            fh.write(_wav_header(0, sample_rate, channels, sampwidth))  # placeholder
    except Exception:
        fh = None
    try:
        for frame in frames:
            if fh is not None:
                try:
                    fh.write(frame)
                    written += len(frame)
                    if written >= header_publish_at:
                        _publish_header()
                except Exception:
                    pass
            yield frame
    finally:
        if fh is not None:
            try:
                _publish_header()
                fh.close()
            except Exception:
                pass
            secs = written / float(sample_rate * channels * sampwidth or 1)
            sys.stderr.write(
                f"recording: {os.path.basename(wav_path)} teed {written} bytes (~{secs:.1f}s)\n"
            )
