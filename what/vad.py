from dataclasses import dataclass
import warnings

warnings.filterwarnings(
    "ignore",
    message="pkg_resources is deprecated as an API.*",
    category=UserWarning,
)

try:
    import webrtcvad  # type: ignore
except ModuleNotFoundError as exc:
    # Newer setuptools builds may not ship pkg_resources; the common
    # webrtcvad wrapper imports it only for __version__. Fall back to the
    # extension module directly so VAD remains usable.
    if exc.name != "pkg_resources":
        raise
    import _webrtcvad

    class _FallbackWebRtcVad:
        class Vad:
            def __init__(self, mode=None):
                self._vad = _webrtcvad.create()
                _webrtcvad.init(self._vad)
                if mode is not None:
                    self.set_mode(mode)

            def set_mode(self, mode):
                _webrtcvad.set_mode(self._vad, mode)

            def is_speech(self, buf, sample_rate, length=None):
                length = length or int(len(buf) / 2)
                if length * 2 > len(buf):
                    raise IndexError(
                        "buffer has %s frames, but length argument was %s"
                        % (int(len(buf) / 2.0), length)
                    )
                return _webrtcvad.process(self._vad, sample_rate, buf, length)

    webrtcvad = _FallbackWebRtcVad()


@dataclass
class VadConfig:
    enabled: bool
    mode: int
    speech_ratio: float


def is_speech_chunk(pcm_bytes: bytes, sample_rate: int, frame_ms: int, vad_cfg: VadConfig) -> bool:
    if not vad_cfg.enabled:
        return True
    if frame_ms not in (10, 20, 30):
        raise ValueError("frame_ms must be 10, 20, or 30 for WebRTC VAD")

    vad = webrtcvad.Vad(vad_cfg.mode)
    frame_bytes = int(sample_rate * frame_ms / 1000) * 2
    if frame_bytes <= 0:
        return True

    voiced = 0
    total = 0
    for i in range(0, len(pcm_bytes) - frame_bytes + 1, frame_bytes):
        frame = pcm_bytes[i : i + frame_bytes]
        total += 1
        if vad.is_speech(frame, sample_rate):
            voiced += 1

    if total == 0:
        return False
    return (voiced / total) >= vad_cfg.speech_ratio
