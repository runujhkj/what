__all__ = ["cli"]

import os as _os

if _os.name == "nt":
    # Before anything spawns: GUI-launched helpers must not pop up console windows.
    from ._win_console import hide_child_consoles as _hide_child_consoles

    _hide_child_consoles()
