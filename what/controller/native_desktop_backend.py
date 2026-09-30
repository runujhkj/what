from __future__ import annotations

import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HELPER_PATH = REPO_ROOT / "bin" / "what-desktop-helper"


def desktop_source_backend() -> str:
    raw = str(os.environ.get("WHAT_DESKTOP_SOURCE_BACKEND", "")).strip().lower()
    if raw in {"native_helper", "legacy_ffmpeg"}:
        return raw
    return "legacy_ffmpeg"


def native_helper_path() -> Path:
    raw = str(os.environ.get("WHAT_DESKTOP_NATIVE_HELPER_PATH", "")).strip()
    if raw:
        return Path(raw).expanduser()
    return DEFAULT_HELPER_PATH


def native_helper_supported() -> bool:
    return sys.platform == "darwin"


def native_helper_ready() -> bool:
    path = native_helper_path()
    return bool(native_helper_supported() and path.exists() and os.access(path, os.X_OK))


def native_helper_capabilities() -> dict[str, object]:
    path = native_helper_path()
    return {
        "desktop_source_backend": desktop_source_backend(),
        "desktop_native_helper_supported": bool(native_helper_supported()),
        "desktop_native_helper_ready": bool(native_helper_ready()),
        "desktop_native_helper_path": str(path),
    }

