import time


class DeadInputDetector:
    """Report a microphone that delivers exact digital silence.

    A working microphone always has a noise floor, even in a quiet room. Sustained
    all-zero PCM instead means the capture is not reaching a live device: a virtual
    input nothing is routed into (e.g. VB-Cable), or macOS denying microphone access,
    which yields zero-filled buffers rather than an error. Whisper then hallucinates
    words such as "you" from the silence, so the service alone cannot reveal this.
    """

    def __init__(self, device: str, threshold_sec: float = 3.0, clock=time.monotonic) -> None:
        self.device = device
        self.threshold_sec = threshold_sec
        self._clock = clock
        self._silent_since: float | None = None
        self._reported = False

    def observe(self, pcm: bytes) -> str | None:
        """Return a warning/recovery line when the input's liveness changes."""
        if pcm.strip(b"\x00"):
            self._silent_since = None
            if self._reported:
                self._reported = False
                return f"capture recovered: mic input '{self.device}' is delivering audio"
            return None
        now = self._clock()
        if self._silent_since is None:
            self._silent_since = now
        if not self._reported and now - self._silent_since >= self.threshold_sec:
            self._reported = True
            return (
                f"capture warning: mic input '{self.device}' is delivering digital silence "
                f"(all-zero audio for {self.threshold_sec:.0f}s). It is likely a virtual or "
                "inactive device, or microphone access is denied for this app. "
                "Choose another mic device in Settings."
            )
        return None
