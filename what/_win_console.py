"""Keep helper processes windowless when `what` runs without a console on Windows.

The GUI starts the controller, clients and capture helpers with no console. A console
program such as ffmpeg or python started from such a process gets a new, visible console
window by default, and closing it kills that process. When this process has no console,
default every subprocess to CREATE_NO_WINDOW; stdio still flows through the pipes/handles
passed to it. Run from a terminal (console present), nothing changes, so child output keeps
reaching that terminal.
"""
from __future__ import annotations

import os
import subprocess


def _has_console() -> bool:
    import ctypes

    return bool(ctypes.windll.kernel32.GetConsoleWindow())


def hide_child_consoles(has_console=None, popen=subprocess.Popen) -> bool:
    """Patch `popen` so children default to CREATE_NO_WINDOW; True if patched."""
    if os.name != "nt" or getattr(popen, "_what_no_window", False):
        return False
    if (has_console or _has_console)():
        return False
    original = popen.__init__

    def __init__(self, *args, **kwargs):
        if len(args) < 14 and not kwargs.get("creationflags"):  # creationflags is 14th positional
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        original(self, *args, **kwargs)

    popen.__init__ = __init__
    popen._what_no_window = True
    return True
