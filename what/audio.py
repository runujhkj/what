import queue
import subprocess
import sys
import threading
from dataclasses import dataclass
from typing import Generator, Iterable

from .boundary_selector import select_cut_samples
from .desktop_audio import build_desktop_input_args
from .live_audio import build_live_ffmpeg_sections

BYTES_PER_SAMPLE = 2  # s16le


@dataclass
class AudioConfig:
    sample_rate: int
    channels: int
    frame_ms: int
    chunk_ms: int
    overlap_ms: int
    boundary_candidate_points: int = 3


@dataclass
class InputConfig:
    mode: str
    mic_backend: str
    mic_device: str
    mic_enabled: bool
    desktop_backend: str
    desktop_device: str
    desktop_enabled: bool
    file_path: str
    stdin_raw: bool
    realtime: bool = False
    # Override the input_source_id the client reports (mic/desktop/mixed) regardless of the
    # capture mode. Lets a launcher feed the MIC via stdin (single-capture fan-out) while
    # still tagging the stream "mic" -- otherwise stdin is hardwired to the desktop lane.
    stream_tag: str | None = None


@dataclass
class Chunk:
    pcm_bytes: bytes
    start_sec: float
    end_sec: float
    cut_samples: int = 0
    boundary_scores: list[tuple[int, float]] | None = None


def build_ffmpeg_cmd(input_cfg: InputConfig, audio_cfg: AudioConfig) -> list[str]:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
    if input_cfg.mode != "stdin":
        cmd += ["-nostdin"]

    if input_cfg.mode == "mic":
        input_args, post_input = build_live_ffmpeg_sections(input_cfg)
        cmd += input_args
        cmd += post_input
    elif input_cfg.mode == "file":
        if not input_cfg.file_path:
            raise ValueError("file_path is required for file input")
        if input_cfg.realtime:
            cmd += ["-re"]
        cmd += ["-i", input_cfg.file_path]
    elif input_cfg.mode == "desktop":
        input_args, post_input = build_live_ffmpeg_sections(input_cfg)
        cmd += input_args
        cmd += post_input
    elif input_cfg.mode == "stdin":
        if input_cfg.stdin_raw:
            cmd += ["-f", "s16le", "-ar", str(audio_cfg.sample_rate), "-ac", str(audio_cfg.channels)]
        cmd += ["-i", "pipe:0"]
    else:
        raise ValueError(f"Unsupported input mode: {input_cfg.mode}")

    cmd += [
        "-ac",
        str(audio_cfg.channels),
        "-ar",
        str(audio_cfg.sample_rate),
        "-f",
        "s16le",
        "-",
    ]
    return cmd


def start_ffmpeg(
    input_cfg: InputConfig,
    audio_cfg: AudioConfig,
    stderr_target=None,
) -> subprocess.Popen:
    cmd = build_ffmpeg_cmd(input_cfg, audio_cfg)
    stdin = sys.stdin.buffer if input_cfg.mode == "stdin" else None
    if stderr_target is None:
        stderr_target = sys.stderr
    proc = subprocess.Popen(
        cmd,
        stdin=stdin,
        stdout=subprocess.PIPE,
        stderr=stderr_target,
        bufsize=0,
    )
    if proc.stdout is None:
        raise RuntimeError("Failed to open ffmpeg stdout")
    return proc


def pcm_frame_generator(proc: subprocess.Popen, frame_samples: int) -> Generator[bytes, None, None]:
    frame_bytes = frame_samples * BYTES_PER_SAMPLE
    assert proc.stdout is not None
    while True:
        data = proc.stdout.read(frame_bytes)
        if not data:
            break
        if len(data) < frame_bytes:
            break
        yield data


def stdin_frame_generator(frame_samples: int) -> Generator[bytes, None, None]:
    """Read pre-formatted PCM frames directly from stdin, bypassing ffmpeg.

    A background thread drains the pipe continuously so the pipe buffer never
    fills during Whisper inference — otherwise the write() in the producer
    (e.g. SCStream callback) blocks, stalling audio delivery.
    """
    frame_bytes = frame_samples * BYTES_PER_SAMPLE
    # Unbounded queue: the stale-chunk-drop in the pipeline handles backlog.
    q: queue.Queue[bytes | None] = queue.Queue()

    def _reader() -> None:
        try:
            buf = sys.stdin.buffer
            while True:
                data = buf.read(frame_bytes)
                if not data or len(data) < frame_bytes:
                    q.put(None)
                    return
                q.put(data)
        except Exception:
            q.put(None)

    threading.Thread(target=_reader, daemon=True, name="stdin-pcm-reader").start()

    while True:
        item = q.get()
        if item is None:
            break
        yield item


def chunk_stream(frames: Iterable[bytes], audio_cfg: AudioConfig) -> Generator[Chunk, None, None]:
    chunk_samples = int(audio_cfg.chunk_ms * audio_cfg.sample_rate / 1000)
    overlap_samples = int(audio_cfg.overlap_ms * audio_cfg.sample_rate / 1000)
    if chunk_samples <= 0:
        raise ValueError("chunk_ms must be > 0")
    if overlap_samples >= chunk_samples:
        raise ValueError("overlap_ms must be less than chunk_ms")

    buffer = bytearray()
    stream_sample = 0

    for frame in frames:
        buffer.extend(frame)
        while len(buffer) >= chunk_samples * BYTES_PER_SAMPLE:
            full_chunk = bytes(buffer[: chunk_samples * BYTES_PER_SAMPLE])
            cut_samples, boundary_scores = select_cut_samples(
                full_chunk,
                sample_rate=audio_cfg.sample_rate,
                chunk_samples=chunk_samples,
                candidate_points=int(audio_cfg.boundary_candidate_points or 1),
            )
            cut_samples = max(overlap_samples + 1, min(chunk_samples, int(cut_samples or chunk_samples)))
            chunk_bytes = full_chunk[: cut_samples * BYTES_PER_SAMPLE]
            start_sec = stream_sample / audio_cfg.sample_rate
            end_sec = start_sec + (cut_samples / audio_cfg.sample_rate)
            yield Chunk(
                pcm_bytes=chunk_bytes,
                start_sec=start_sec,
                end_sec=end_sec,
                cut_samples=cut_samples,
                boundary_scores=boundary_scores,
            )

            step_samples = max(1, cut_samples - overlap_samples)
            drop_bytes = step_samples * BYTES_PER_SAMPLE
            buffer = buffer[drop_bytes:]
            stream_sample += step_samples
