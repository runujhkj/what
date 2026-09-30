import json
import sys
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class OutputConfig:
    text_stream: bool
    jsonl_log: str
    jsonl_dir: str
    text_mode: str = "delta"
    text_window_segments: int = 0
    text_window_chars: int = 0
    text_block_clear: bool = False
    text_normalize: bool = False


class OutputManager:
    def __init__(self, cfg: OutputConfig) -> None:
        self.cfg = cfg
        self._last_text = ""
        self._segments: list[str] = []
        self._log_fh = None
        if cfg.jsonl_log:
            self._log_fh = open(cfg.jsonl_log, "a", encoding="ascii")

    def close(self) -> None:
        if self._log_fh:
            self._log_fh.close()

    def write_event(self, event: dict[str, Any]) -> None:
        if self.cfg.text_stream:
            self._write_text(event)
        if self._log_fh:
            event_with_wall = dict(event)
            event_with_wall["wall_time"] = time.time()
            self._log_fh.write(json.dumps(event_with_wall, ensure_ascii=True) + "\n")
            self._log_fh.flush()

    def enrich_event(self, event: dict[str, Any]) -> dict[str, Any]:
        text = event.get("text", "")
        if not text:
            return event
        mode = (self.cfg.text_mode or "delta").lower()
        emit_display = (
            mode != "delta"
            or self.cfg.text_normalize
            or self.cfg.text_block_clear
            or self.cfg.text_window_segments > 0
            or self.cfg.text_window_chars > 0
        )
        if not emit_display:
            return event
        display_text = text
        if self.cfg.text_normalize:
            display_text = _normalize_text(display_text)
        if mode == "block":
            self._segments.append(display_text)
            if self.cfg.text_window_segments > 0:
                self._segments = self._segments[-self.cfg.text_window_segments :]
            display_text = " ".join(self._segments).strip()
            if self.cfg.text_window_chars > 0 and len(display_text) > self.cfg.text_window_chars:
                display_text = display_text[-self.cfg.text_window_chars :].lstrip()
        event["display_text"] = display_text
        event["display_mode"] = mode
        event["display_clear"] = self.cfg.text_block_clear
        return event

    def _write_text(self, event: dict[str, Any]) -> None:
        text = event.get("display_text") or event.get("text", "")
        if not text:
            return
        mode = event.get("display_mode") or (self.cfg.text_mode or "delta").lower()
        if mode == "delta":
            delta = _delta_text(self._last_text, text)
            if delta:
                sys.stdout.write(delta + "\n")
                sys.stdout.flush()
            self._last_text = text
            return
        if mode == "block":
            if event.get("display_clear") and sys.stdout.isatty():
                sys.stdout.write("\033[H\033[J")
            sys.stdout.write(text + "\n")
            sys.stdout.flush()
            self._last_text = text
            return
        sys.stdout.write(text + "\n")
        sys.stdout.flush()
        self._last_text = text


def _delta_text(prev: str, current: str) -> str:
    if not prev:
        return current
    max_check = min(len(prev), len(current))
    for k in range(max_check, 0, -1):
        if prev.endswith(current[:k]):
            return current[k:]
    return current


def _normalize_text(text: str) -> str:
    cleaned = text.translate(str.maketrans("", "", ".?!;:"))
    return " ".join(cleaned.split())


def format_sse(event: dict[str, Any]) -> str:
    payload = json.dumps(event, ensure_ascii=True)
    return f"data: {payload}\n\n"
