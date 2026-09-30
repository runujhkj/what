"""GUI-launched helpers on Windows start children without new console windows."""
import subprocess

import pytest

from what import _win_console


class FakePopen:
    def __init__(self, *args, **kwargs):
        self.args, self.kwargs = args, kwargs


@pytest.fixture
def popen():
    class P(FakePopen):
        pass
    return P


def test_no_console_defaults_children_to_create_no_window(monkeypatch, popen):
    monkeypatch.setattr(_win_console.os, "name", "nt")
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    assert _win_console.hide_child_consoles(has_console=lambda: False, popen=popen)
    assert popen(["ffmpeg"]).kwargs["creationflags"] == 0x08000000
    assert popen(["ffmpeg"], creationflags=0x10).kwargs["creationflags"] == 0x10  # explicit wins
    assert not _win_console.hide_child_consoles(has_console=lambda: False, popen=popen)  # once


def test_terminal_launch_is_untouched(monkeypatch, popen):
    monkeypatch.setattr(_win_console.os, "name", "nt")
    assert not _win_console.hide_child_consoles(has_console=lambda: True, popen=popen)
    assert "creationflags" not in popen(["ffmpeg"]).kwargs


def test_non_windows_is_untouched(monkeypatch, popen):
    monkeypatch.setattr(_win_console.os, "name", "posix")
    assert not _win_console.hide_child_consoles(has_console=lambda: False, popen=popen)
