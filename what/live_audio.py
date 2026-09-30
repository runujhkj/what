import re
import subprocess

from .desktop_audio import build_desktop_input_args, build_dshow_mic_args


def _norm_device_name(s: str) -> str:
    # Fold the apostrophe variants (macOS device names use U+2019 "'", users type U+0027
    # "'") plus case/whitespace, so a typed name still matches the real device.
    s = s.replace("’", "'").replace("‘", "'").replace("ʼ", "'")
    return " ".join(s.split()).casefold()


def _avf_resolve_index(name: str):
    """Match an avfoundation audio-device NAME to its index, tolerant of curly-vs-straight
    apostrophes and case/whitespace (a typed "Studio Mic's Input" must still open the real
    device named with a curly apostrophe). Returns the index string, or None if no match."""
    try:
        out = subprocess.run(
            ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
            capture_output=True, text=True).stderr or ""
    except Exception:
        return None
    target = _norm_device_name(name)
    in_audio = False
    for line in out.splitlines():
        if "AVFoundation audio devices" in line:
            in_audio = True
            continue
        if in_audio and "AVFoundation video devices" in line:
            break
        if in_audio:
            m = re.search(r"\[(\d+)\]\s+(.*)$", line)
            if m and _norm_device_name(m.group(2)) == target:
                return m.group(1)
    return None


def _avf_mic_device(device) -> str:
    """avfoundation inputs are "[video]:[audio]". A bare device name or index is an
    audio-only device, so it needs a leading ':' -- without it ffmpeg reads e.g.
    'MacBook Pro Microphone' as a *video* device ("Video device not found"). A NAME is
    resolved to its current index (indexes are unambiguous and drift between runs), so
    apostrophe/case differences don't cause "Audio device not found".

    "default" is avfoundation's own `:default`, the macOS default input. Index 0 is
    just whichever device is listed first -- often a virtual cable -- and it shifts
    as devices are added or removed."""
    if device in ("default", "", None):
        return ":default"
    device = str(device)
    if ":" in device:
        return device  # already "[video]:[audio]"
    if device.strip().isdigit():
        return ":" + device.strip()
    idx = _avf_resolve_index(device)
    if idx is not None:
        return ":" + idx
    return ":" + device  # fall back to the raw name


def resolve_live_source_flags(input_cfg) -> tuple[bool, bool]:
    if input_cfg.mode in {"file", "stdin"}:
        return False, False
    mic_enabled = bool(input_cfg.mic_enabled)
    desktop_enabled = bool(input_cfg.desktop_enabled)
    if not mic_enabled and not desktop_enabled:
        if input_cfg.mode == "desktop":
            desktop_enabled = True
        else:
            mic_enabled = True
    return mic_enabled, desktop_enabled


def build_live_ffmpeg_sections(input_cfg) -> tuple[list[str], list[str]]:
    mic_enabled, desktop_enabled = resolve_live_source_flags(input_cfg)
    sections: list[str] = []
    post_input: list[str] = []
    if mic_enabled:
        if input_cfg.mic_backend == "pulse":
            sections += ["-f", "pulse", "-i", input_cfg.mic_device]
        elif input_cfg.mic_backend == "alsa":
            sections += ["-f", "alsa", "-i", input_cfg.mic_device]
        elif input_cfg.mic_backend == "avfoundation":
            device = _avf_mic_device(input_cfg.mic_device)
            sections += ["-f", "avfoundation", "-i", device]
        elif input_cfg.mic_backend == "dshow":
            sections += build_dshow_mic_args(input_cfg.mic_device)
        else:
            raise ValueError(f"Unsupported mic backend: {input_cfg.mic_backend}")
    if desktop_enabled:
        sections += build_desktop_input_args(input_cfg.desktop_backend, input_cfg.desktop_device)

    source_count = int(mic_enabled) + int(desktop_enabled)
    if source_count <= 1:
        return sections, post_input

    if not (
        input_cfg.mic_backend == "avfoundation"
        and input_cfg.desktop_backend == "avfoundation"
    ):
        raise ValueError("Mixed mic+desktop capture is currently implemented for macOS avfoundation only")

    # Mixed capture policy: mic-priority without starving desktop.
    # Keep mic dominant in overlap, but avoid suppressing desktop to near-zero
    # when mic input is merely present/noisy.
    post_input = [
        "-filter_complex",
        "[0:a]volume=1.6[mic];"
        "[1:a]volume=0.95[desk];"
        "[desk][mic]sidechaincompress=threshold=0.020:ratio=8:attack=8:release=180[deskduck];"
        "[mic][deskduck]amix=inputs=2:weights='1.0 0.45':normalize=0:duration=longest:dropout_transition=0[mix]",
        "-map",
        "[mix]",
    ]
    return sections, post_input


def describe_live_capture_graph(input_cfg) -> tuple[int, bool, str]:
    mic_enabled, desktop_enabled = resolve_live_source_flags(input_cfg)
    inputs = int(mic_enabled) + int(desktop_enabled)
    mixed = inputs > 1
    return inputs, mixed, str(getattr(input_cfg, "mode", "") or "")
