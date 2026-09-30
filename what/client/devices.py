import re
import subprocess
import sys
import shutil

from ..audio import InputConfig
from ..desktop_audio import list_desktop_devices, list_dshow_mic_devices, normalize_desktop_backend


def _parse_avfoundation_devices(output: str) -> list[str]:
    devices = []
    in_audio = False
    for line in output.splitlines():
        if "AVFoundation audio devices" in line:
            in_audio = True
            continue
        if in_audio and "AVFoundation video devices" in line:
            break
        if in_audio:
            match = re.search(r"\[(\d+)\]\s+(.*)$", line)
            if match:
                devices.append(f"{match.group(1)}: {match.group(2)}")
    return devices


def _list_mic_devices(input_cfg: InputConfig) -> list[str]:
    backend = input_cfg.mic_backend
    if backend == "avfoundation":
        cmd = ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""]
        result = subprocess.run(cmd, capture_output=True, text=True)
        output = result.stderr or result.stdout or ""
        return _parse_avfoundation_devices(output)
    if backend == "pulse":
        if shutil.which("pactl"):
            result = subprocess.run(["pactl", "list", "sources", "short"], capture_output=True, text=True)
            devices = []
            for line in result.stdout.splitlines():
                parts = line.split("\t")
                if len(parts) >= 2:
                    devices.append(parts[1])
            return devices
        if shutil.which("pacmd"):
            result = subprocess.run(["pacmd", "list-sources"], capture_output=True, text=True)
            devices = []
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith("name:"):
                    devices.append(line.split("name:", 1)[1].strip().strip("<>"))
            return devices
        return []
    if backend == "dshow":
        return list_dshow_mic_devices()
    if backend == "alsa":
        if shutil.which("arecord"):
            result = subprocess.run(["arecord", "-l"], capture_output=True, text=True)
            devices = []
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith("card ") and "device" in line:
                    devices.append(line)
            return devices
        return []
    return []


def print_mic_info(input_cfg: InputConfig) -> None:
    sys.stderr.write(f"mic backend: {input_cfg.mic_backend}\n")
    devices = _list_mic_devices(input_cfg)
    resolved_device = input_cfg.mic_device
    if input_cfg.mic_device == "default" and devices:
        for device in devices:
            if ".monitor" not in device:
                resolved_device = device
                break
        if resolved_device == "default":
            resolved_device = devices[0]
    if input_cfg.mic_device == "default" and resolved_device != "default":
        sys.stderr.write(f"mic device: default ({resolved_device})\n")
        needle = resolved_device
    else:
        sys.stderr.write(f"mic device: {input_cfg.mic_device}\n")
        needle = input_cfg.mic_device
    if not devices:
        sys.stderr.write("available mic devices: (unavailable)\n")
        return
    sys.stderr.write("available mic devices:\n")
    for device in devices:
        marker = "-"
        if needle and (needle in device or device.startswith(f"{needle.strip(':')}:")):
            marker = "*"
        sys.stderr.write(f"  {marker} {device}\n")


def print_desktop_info(input_cfg: InputConfig) -> None:
    backend = normalize_desktop_backend(input_cfg.desktop_backend)
    sys.stderr.write(f"desktop backend: {backend}\n")
    sys.stderr.write(f"desktop device: {input_cfg.desktop_device or '(unset)'}\n")
    devices = list_desktop_devices(backend)
    if not devices:
        sys.stderr.write("available desktop devices: (unavailable)\n")
        return
    sys.stderr.write("available desktop devices:\n")
    needle = (input_cfg.desktop_device or "").strip()
    for device in devices:
        marker = "-"
        if needle and (needle in device or device.startswith(f"{needle.strip(':')}:")):
            marker = "*"
        sys.stderr.write(f"  {marker} {device}\n")
