import subprocess
from typing import Callable

from ..audio import AudioConfig, InputConfig
from ..asr import AsrConfig
from ..output import OutputConfig
from ..pipeline import run_pipeline
from ..vad import VadConfig


def transcribe_file_streaming(
    audio_path: str,
    audio_cfg: AudioConfig,
    vad_cfg: VadConfig,
    asr_cfg: AsrConfig,
    on_delta: Callable[[str], None] | None = None,
) -> str:
    input_cfg = InputConfig(
        mode="file",
        mic_backend="pulse",
        mic_device="default",
        mic_enabled=False,
        desktop_backend="avfoundation",
        desktop_device="default",
        desktop_enabled=False,
        file_path=audio_path,
        stdin_raw=False,
        realtime=False,
    )
    output_cfg = OutputConfig(text_stream=False, jsonl_log="", jsonl_dir="")

    full_text: list[str] = []
    last_text = ""

    def on_event(event: dict) -> None:
        nonlocal last_text
        text = event.get("text", "")
        delta = _delta_text(last_text, text)
        if delta:
            full_text.append(delta)
            if on_delta:
                on_delta(delta)
        last_text = text

    run_pipeline(
        audio_cfg=audio_cfg,
        input_cfg=input_cfg,
        vad_cfg=vad_cfg,
        asr_cfg=asr_cfg,
        output_cfg=output_cfg,
        on_event=on_event,
        stderr_target=subprocess.DEVNULL,
    )

    return " ".join(full_text).strip()


def _delta_text(prev: str, current: str) -> str:
    if not prev:
        return current
    max_check = min(len(prev), len(current))
    for k in range(max_check, 0, -1):
        if prev.endswith(current[:k]):
            return current[k:]
    return current
