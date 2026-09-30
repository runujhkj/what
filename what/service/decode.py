import subprocess
import sys

from ..audio import AudioConfig


def start_opus_decoder(audio_cfg: AudioConfig):
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "ogg",
        "-i",
        "pipe:0",
        "-ac",
        str(audio_cfg.channels),
        "-ar",
        str(audio_cfg.sample_rate),
        "-f",
        "s16le",
        "-",
    ]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        bufsize=0,
    )
    if proc.stdout is None or proc.stdin is None:
        raise RuntimeError("Failed to open ffmpeg pipes")
    return proc
