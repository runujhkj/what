import subprocess
import sys

from ..audio import AudioConfig, InputConfig, build_ffmpeg_cmd
from ..live_audio import build_live_ffmpeg_sections


def build_opus_cmd(input_cfg: InputConfig, audio_cfg: AudioConfig) -> list[str]:
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
        "-c:a",
        "libopus",
        "-b:a",
        "24k",
        "-f",
        "ogg",
        "-",
    ]
    return cmd


def start_capture(
    input_cfg: InputConfig,
    audio_cfg: AudioConfig,
    transport: str,
) -> subprocess.Popen:
    if transport == "pcm":
        cmd = build_ffmpeg_cmd(input_cfg, audio_cfg)
    elif transport == "opus":
        cmd = build_opus_cmd(input_cfg, audio_cfg)
    else:
        raise ValueError(f"Unsupported transport: {transport}")

    stdin = sys.stdin.buffer if input_cfg.mode == "stdin" else None
    proc = subprocess.Popen(
        cmd,
        stdin=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
    if proc.stdout is None:
        raise RuntimeError("Failed to open ffmpeg stdout")
    return proc
