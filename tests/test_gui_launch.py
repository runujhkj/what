"""`what gui` launches the locally installed Electron without needing npm on PATH."""
from what.cli.handle_gui import gui_command


def _install_electron(gui_dir, name="electron.exe"):
    pkg = gui_dir / "node_modules" / "electron"
    (pkg / "dist").mkdir(parents=True)
    (pkg / "path.txt").write_text(name, encoding="utf-8")
    (pkg / "dist" / name).write_bytes(b"")
    return pkg / "dist" / name


def test_prefers_local_electron_binary(tmp_path):
    exe = _install_electron(tmp_path)
    assert gui_command(str(tmp_path)) == [str(exe), str(tmp_path)]


def test_falls_back_to_npm_start_without_node_modules(tmp_path):
    cmd = gui_command(str(tmp_path))
    assert cmd[1:] == ["--prefix", str(tmp_path), "run", "start"]


def test_explicit_npm_bin_wins(tmp_path):
    _install_electron(tmp_path)
    assert gui_command(str(tmp_path), "custom-npm")[1:] == ["--prefix", str(tmp_path), "run", "start"]


def test_refreshed_windows_path_appends_new_registry_entries():
    from what.cli.handle_gui import refreshed_windows_path

    sep = chr(92)  # backslash
    current = ";".join(["C:" + sep + "Windows", "C:" + sep + "Python312" + sep])
    registry = ["c:" + sep + "windows", "C:" + sep + "Python312", "C:" + sep + "nodejs", "C:" + sep + "ffmpeg"]
    out = refreshed_windows_path(current, read_registry=lambda: registry).split(";")
    # Existing entries kept as-is; case/trailing-separator duplicates skipped; new ones appended.
    assert out == current.split(";") + ["C:" + sep + "nodejs", "C:" + sep + "ffmpeg"]
