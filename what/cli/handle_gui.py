import os
import shutil
import socket
import subprocess
import sys
import time

from ..env import get_env, get_env_int


def handle_gui(args) -> None:
    from ..cuda_runtime import prepare_cuda_environment
    if os.name == "nt":
        os.environ["PATH"] = refreshed_windows_path(os.environ.get("PATH", ""))
    # Complete first-time downloads before the GUI starts its readiness timeout.
    os.environ.update(prepare_cuda_environment())
    control_host = args.control_host or get_env("WHAT_CONTROL_HOST") or "127.0.0.1"
    control_port = args.control_port or get_env_int("WHAT_CONTROL_PORT") or 8780
    service_host = args.service_host or get_env("WHAT_SERVICE_HOST") or "127.0.0.1"
    service_port = args.service_port or get_env_int("WHAT_SERVICE_PORT") or 8765
    npm_bin = args.npm_bin or get_env("WHAT_GUI_NPM")
    gui_dir = args.gui_dir or get_env("WHAT_GUI_DIR") or "gui"
    gui_cmd = gui_command(gui_dir, npm_bin)

    control_cmd = [
        sys.executable,
        "-m",
        "what",
        "control",
        "--host",
        control_host,
        "--port",
        str(control_port),
        "--service-host",
        service_host,
        "--service-port",
        str(service_port),
    ]

    control_proc = None
    if _is_port_open(control_host, int(control_port)):
        sys.stderr.write(
            f"what gui: controller already running at {control_host}:{control_port}; reusing it\n"
        )
    else:
        control_proc = subprocess.Popen(control_cmd, stdout=sys.stdout, stderr=sys.stderr)
        time.sleep(0.5)
    try:
        gui_env = dict(os.environ)
        gui_env["WHAT_PYTHON"] = sys.executable
        gui_proc = subprocess.Popen(gui_cmd, stdout=sys.stdout, stderr=sys.stderr, env=gui_env)
    except FileNotFoundError as exc:
        if control_proc is not None:
            control_proc.terminate()
        raise SystemExit(
            f"Failed to start GUI ({gui_cmd[0]}): {exc}. Install the GUI dependencies with "
            f"`npm --prefix {gui_dir} ci` (the setup script does this), then retry."
        ) from exc

    try:
        gui_proc.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if gui_proc.poll() is None:
            gui_proc.terminate()
        if control_proc is not None and control_proc.poll() is None:
            control_proc.terminate()
        try:
            gui_proc.wait(timeout=2)
        except Exception:
            gui_proc.kill()
        if control_proc is not None:
            try:
                control_proc.wait(timeout=2)
            except Exception:
                control_proc.kill()


def refreshed_windows_path(current: str, read_registry=None) -> str:
    """`current` PATH plus entries added to the machine/user PATH since this shell started.

    A terminal opened before the setup script installed FFmpeg/Node with winget keeps its
    old PATH; the GUI and its capture helpers would then fail to find ffmpeg.
    """
    if read_registry is None:
        read_registry = _registry_paths
    parts = [p for p in current.split(";") if p]
    seen = {p.rstrip("\\").lower() for p in parts}
    for entry in read_registry():
        expanded = os.path.expandvars(entry)
        key = expanded.rstrip("\\").lower()
        if expanded and key not in seen:
            parts.append(expanded)
            seen.add(key)
    return ";".join(parts)


def _registry_paths() -> list[str]:
    import winreg

    out = []
    for hive, sub in ((winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
                      (winreg.HKEY_CURRENT_USER, "Environment")):
        try:
            with winreg.OpenKey(hive, sub) as key:
                value, _ = winreg.QueryValueEx(key, "Path")
            out.extend(p for p in str(value).split(";") if p)
        except OSError:
            continue
    return out


def electron_binary(gui_dir: str) -> str | None:
    """The Electron executable `npm ci` installed under gui/, if present.

    Launching it directly (what `npm start` does) needs neither npm nor Node on PATH,
    which a terminal opened before Node was installed would lack.
    """
    pkg = os.path.join(gui_dir, "node_modules", "electron")
    try:
        with open(os.path.join(pkg, "path.txt"), encoding="utf-8") as f:
            rel = f.read().strip()
    except OSError:
        return None
    exe = os.path.join(pkg, "dist", rel)
    return exe if rel and os.path.isfile(exe) else None


def gui_command(gui_dir: str, npm_bin: str | None = None) -> list[str]:
    if not npm_bin:
        exe = electron_binary(gui_dir)
        if exe:
            return [exe, gui_dir]
        npm_bin = "npm"
    # Windows ships npm as npm.cmd, which CreateProcess won't find from a bare "npm".
    return [shutil.which(npm_bin) or npm_bin, "--prefix", gui_dir, "run", "start"]


def _is_port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False
