import platform
import re
import shutil
import subprocess
from typing import List


def default_desktop_backend() -> str:
    system = platform.system().lower()
    if system == "darwin":
        return "avfoundation"
    if system == "linux":
        return "pulse"
    if system == "windows":
        return "wasapi"
    return "avfoundation"


def default_mic_backend() -> str:
    system = platform.system().lower()
    if system == "darwin":
        return "avfoundation"
    if system == "windows":
        return "dshow"
    return "pulse"


def normalize_desktop_backend(value: str | None) -> str:
    text = (value or "").strip().lower()
    # "auto" is the portable way to say "whatever this machine uses". A shared config
    # naming a concrete backend (the old default.toml said "avfoundation") silently
    # defeats default_desktop_backend() everywhere except the platform it was written on.
    if not text or text == "auto":
        return default_desktop_backend()
    if text in {"avfoundation", "pulse", "wasapi"}:
        return text
    return text


def _pactl_available() -> bool:
    return bool(shutil.which("pactl"))


def _pulse_sources() -> List[str]:
    """Every PulseAudio/PipeWire source name (pactl list sources short, field 1)."""
    try:
        out = subprocess.run(["pactl", "list", "sources", "short"],
                             capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return []
    return [parts[1] for parts in (line.split("\t") for line in out.splitlines())
            if len(parts) >= 2]


def _pulse_default_monitor() -> str | None:
    """The monitor source of the default sink -- i.e. "what is currently playing".

    That is the Linux equivalent of the macOS desktop tap: a sink's .monitor source
    carries everything mixed to that output.
    """
    sink = ""
    try:
        sink = subprocess.run(["pactl", "get-default-sink"],
                              capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        sink = ""
    if not sink or sink.startswith("Failure"):
        # Older pactl has no get-default-sink; `pactl info` reports it either way.
        try:
            info = subprocess.run(["pactl", "info"], capture_output=True, text=True,
                                  timeout=5).stdout
        except Exception:
            return None
        sink = ""
        for line in info.splitlines():
            if line.startswith("Default Sink:"):
                sink = line.split(":", 1)[1].strip()
                break
    if not sink:
        return None
    monitor = f"{sink}.monitor"
    sources = _pulse_sources()
    if monitor in sources or not sources:
        return monitor
    # The sink name occasionally differs from its monitor's prefix; take any monitor.
    for name in sources:
        if name.endswith(".monitor"):
            return name
    return None


# --- Windows (WASAPI loopback via DirectShow) ---------------------------------------
#
# ffmpeg has no native WASAPI loopback input, so on Windows we capture system audio through
# a DirectShow loopback-capable device: the built-in "Stereo Mix", or a virtual capture
# device (VB-Cable's "CABLE Output", screen-capture-recorder's "virtual-audio-capturer").
# A future driverless option is a native WASAPI helper (like the macOS CoreAudio tap) or
# pyaudiowpatch; this keeps the existing ffmpeg-PCM architecture and needs no new dependency.

_LOOPBACK_HINTS = (
    "stereo mix",
    "what u hear",
    "wave out mix",
    "virtual-audio-capturer",
    "cable output",
    "loopback",
)


def _parse_dshow_audio_devices(output: str) -> List[str]:
    """DirectShow audio device names from `ffmpeg -list_devices` stderr.

    Handles both layouts ffmpeg has used: a "DirectShow audio devices" section header, and
    per-line "(audio)" tags. The '@device_...' alternative-name lines are skipped.
    """
    devices: List[str] = []
    in_audio = False
    for line in output.splitlines():
        low = line.lower()
        if "directshow audio devices" in low:
            in_audio = True
            continue
        if "directshow video devices" in low:
            in_audio = False
            continue
        if "alternative name" in low:
            continue
        match = re.search(r'"([^"]+)"', line)
        if not match:
            continue
        if in_audio or low.rstrip().endswith("(audio)"):
            devices.append(match.group(1))
    return devices


def _dshow_audio_devices() -> List[str]:
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
            capture_output=True, text=True, timeout=10)
    except Exception:
        return []
    # -list_devices exits non-zero (the dummy input fails) but prints the list to stderr.
    return _parse_dshow_audio_devices((result.stderr or "") + (result.stdout or ""))


def _windows_default_loopback(devices: List[str]) -> str | None:
    for name in devices:
        low = name.lower()
        if any(hint in low for hint in _LOOPBACK_HINTS):
            return name
    return None


def list_dshow_mic_devices() -> List[str]:
    """DirectShow audio inputs, microphones first (loopback devices are desktop sources)."""
    devices = _dshow_audio_devices()
    mics = [d for d in devices if not any(h in d.lower() for h in _LOOPBACK_HINTS)]
    return mics + [d for d in devices if d not in mics]


def build_dshow_mic_args(device: str, devices: List[str] | None = None) -> list[str]:
    """ffmpeg input args for a Windows microphone by DirectShow name.

    DirectShow has no "default" alias, so "default" picks the first non-loopback input.
    A 50 ms capture buffer replaces DirectShow's ~500 ms default, which would add that
    much latency to live captions.
    """
    dev = (device or "").strip()
    if not dev or dev == "default":
        candidates = list_dshow_mic_devices() if devices is None else devices
        dev = next((d for d in candidates if not any(h in d.lower() for h in _LOOPBACK_HINTS)), "")
    if not dev:
        raise ValueError(
            "No microphone found. Connect a microphone and check Windows Settings > Privacy & "
            "security > Microphone allows desktop apps to use it."
        )
    return ["-f", "dshow", "-audio_buffer_size", "50", "-i", f"audio={dev}"]


def build_desktop_input_args(backend: str, device: str) -> list[str]:
    selected = normalize_desktop_backend(backend)
    if selected == "avfoundation":
        dev = (device or "").strip()
        if not dev or dev == "default":
            raise ValueError(
                "Desktop audio device is not configured. Select a desktop capture device explicitly."
            )
        return ["-f", "avfoundation", "-i", dev]
    if selected == "pulse":
        if not _pactl_available():
            raise ValueError(
                "Desktop audio capture needs pactl (pulseaudio-utils) to find the output "
                "monitor source; install it or name a monitor source explicitly."
            )
        dev = (device or "").strip()
        if not dev or dev == "default":
            dev = _pulse_default_monitor() or ""
        if not dev:
            raise ValueError(
                "No PulseAudio monitor source found for the default sink -- nothing is "
                "playing to a capturable output."
            )
        return ["-f", "pulse", "-i", dev]
    if selected == "wasapi":
        dev = (device or "").strip()
        if not dev or dev == "default":
            dev = _windows_default_loopback(_dshow_audio_devices()) or ""
        if not dev:
            raise ValueError(
                "No system-audio loopback device found. Enable 'Stereo Mix' in Windows Sound "
                "settings (Recording devices), or install a virtual audio device such as "
                "VB-Cable, then select it as the desktop capture device."
            )
        return ["-f", "dshow", "-i", f"audio={dev}"]
    raise ValueError(f"Unsupported desktop backend: {backend}")


def _parse_avfoundation_audio_devices(output: str) -> List[str]:
    devices: List[str] = []
    in_audio = False
    for line in output.splitlines():
        if "AVFoundation audio devices" in line:
            in_audio = True
            continue
        if in_audio and "AVFoundation video devices" in line:
            break
        if not in_audio:
            continue
        match = re.search(r"\[(\d+)\]\s+(.*)$", line)
        if match:
            devices.append(f"{match.group(1)}: {match.group(2)}")
    return devices


def list_desktop_devices(backend: str) -> list[str]:
    selected = normalize_desktop_backend(backend)
    if selected == "avfoundation":
        cmd = ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""]
        result = subprocess.run(cmd, capture_output=True, text=True)
        output = result.stderr or result.stdout or ""
        return _parse_avfoundation_audio_devices(output)
    if selected == "pulse":
        if not _pactl_available():
            return []
        # Only monitors: a plain input is a mic, which is the other stream's job.
        return [name for name in _pulse_sources() if name.endswith(".monitor")]
    if selected == "wasapi":
        # All DirectShow audio inputs; the user picks their loopback / virtual-cable device.
        return _dshow_audio_devices()
    return []
