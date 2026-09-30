import os
import re
from datetime import datetime

from ..audio import AudioConfig
from ..asr import AsrConfig
from ..vad import VadConfig


def ensure_log_dir(path: str) -> None:
    if not path:
        return
    log_dir = os.path.dirname(path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)


def make_log_path(prefix: str, log_dir: str = "logs") -> str:
    os.makedirs(log_dir, exist_ok=True)
    now = datetime.now()
    date = now.strftime("%y%m%d")
    time_part = now.strftime("%H%M%S")
    existing = [
        name
        for name in os.listdir(log_dir)
        if name.startswith(f"{prefix}-{date}-") and name.endswith(".jsonl")
    ]
    index = len(existing) + 1
    return os.path.join(log_dir, f"{prefix}-{date}-{index}-{time_part}.jsonl")


def make_session_label(log_dir: str = "logs") -> str:
    os.makedirs(log_dir, exist_ok=True)
    now = datetime.now()
    day = now.strftime("%Y-%m-%d")
    time_part = now.strftime("T%H%M%S")
    pattern = re.compile(rf"^{re.escape(day)}_(\d+)_T\d{{6}}$")
    existing_indices: list[int] = []
    for name in os.listdir(log_dir):
        match = pattern.match(name)
        if not match:
            continue
        existing_indices.append(int(match.group(1)))
    index = (max(existing_indices) + 1) if existing_indices else 1
    return f"{day}_{index:03d}_{time_part}"


def tune_suggestion(sub: int, ins: int, delete: int, audio_cfg: AudioConfig, vad_cfg: VadConfig, asr_cfg: AsrConfig) -> str:
    if ins >= sub and ins >= delete:
        next_no_speech = min(asr_cfg.no_speech_threshold + 0.1, 0.9)
        next_ratio = min(vad_cfg.speech_ratio + 0.1, 0.6)
        next_overlap = max(audio_cfg.overlap_ms - 200, 0)
        stutter_hint = ""
        if audio_cfg.overlap_ms > 0:
            stutter_hint = (
                f" time-travel stutter likely; overlap_ms={audio_cfg.overlap_ms} "
                f"-> try --overlap-ms {next_overlap}"
            )
        return (
            "suggestion: high insertions; current "
            f"no_speech_threshold={asr_cfg.no_speech_threshold} vad.speech_ratio={vad_cfg.speech_ratio} "
            f"overlap_ms={audio_cfg.overlap_ms}; try "
            f"--no-speech-threshold {next_no_speech} --vad-speech-ratio {next_ratio} --vad-mode 3 "
            f"--overlap-ms {next_overlap}.{stutter_hint}"
        )
    if delete >= sub and delete >= ins:
        next_no_speech = max(asr_cfg.no_speech_threshold - 0.1, 0.1)
        next_ratio = max(vad_cfg.speech_ratio - 0.05, 0.05)
        next_chunk = audio_cfg.chunk_ms + 200
        return (
            "suggestion: high deletions; current "
            f"no_speech_threshold={asr_cfg.no_speech_threshold} vad.speech_ratio={vad_cfg.speech_ratio} "
            f"chunk_ms={audio_cfg.chunk_ms}; try "
            f"--no-speech-threshold {next_no_speech} --vad-speech-ratio {next_ratio} --chunk-ms {next_chunk}"
        )
    next_beam = asr_cfg.beam_size + 2
    return (
        "suggestion: high substitutions; current "
        f"model={asr_cfg.model_size} beam_size={asr_cfg.beam_size}; try "
        f"--model large-v2 --beam-size {next_beam}"
    )
