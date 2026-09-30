import sys
import threading
import time

from .live_audio_probe import measure_live_sources


class LiveAudioMeter:
    def __init__(self, input_cfg, audio_cfg, stop_event: threading.Event, interval_sec: float = 0.8):
        self.input_cfg = input_cfg
        self.audio_cfg = audio_cfg
        self.stop_event = stop_event
        self.interval_sec = max(0.4, float(interval_sec))
        self._thread: threading.Thread | None = None
        self._last_line = ""
        self._last_emit_at = 0.0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def join(self, timeout: float = 0.5) -> None:
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    # Re-emit an unchanged reading after this long. Consumers use the line's arrival
    # time as "audio is flowing right now" (e.g. a GUI driving an Audio-in indicator off
    # mic-status.json's updated_at with a 2s window), so suppressing repeats indefinitely
    # made a steady level look like the capture had stopped.
    REPEAT_AFTER_SEC = 1.5

    def _emit(self, line: str) -> None:
        text = str(line or "").strip()
        if not text:
            return
        now = time.monotonic()
        if text == self._last_line and (now - self._last_emit_at) < self.REPEAT_AFTER_SEC:
            return
        self._last_line = text
        self._last_emit_at = now
        sys.stderr.write(text + "\n")
        sys.stderr.flush()

    def _run(self) -> None:
        while not self.stop_event.is_set():
            try:
                levels = measure_live_sources(self.input_cfg, self.audio_cfg, duration_sec=0.18)
                parts: list[str] = []
                for name in ("mic", "desktop"):
                    if name not in levels:
                        continue
                    entry = levels[name] or {}
                    level = entry.get("level", -1)
                    state = entry.get("state", "error")
                    parts.append(f"{name}={level}")
                    parts.append(f"{name}_state={state}")
                if parts:
                    self._emit("capture level: " + " ".join(parts))
            except Exception as err:
                self._emit(f"capture level warning: {err}")
            if self.stop_event.wait(self.interval_sec):
                break
