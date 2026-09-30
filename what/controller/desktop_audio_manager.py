import json
import os
import subprocess
import sys
from pathlib import Path

from . import audio_routing_manager
from .desktop_audio_actions import install_action, uninstall_action

HAL_DIR = Path("/Library/Audio/Plug-Ins/HAL")


def _is_mac() -> bool:
    return sys.platform == "darwin"


def _list_hal_drivers() -> list[str]:
    try:
        return sorted([x.name for x in HAL_DIR.iterdir() if x.is_dir() and x.name.lower().endswith(".driver")])
    except Exception:
        return []


def _is_known_loopback_driver(name: str) -> bool:
    text = str(name or "").lower()
    return ("blackhole" in text) or ("loopback" in text) or ("soundflower" in text)


def _find_installed_loopback_drivers() -> list[str]:
    return [name for name in _list_hal_drivers() if _is_known_loopback_driver(name)]


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _run_admin(command: str) -> subprocess.CompletedProcess:
    script = f'do shell script "{command.replace(chr(34), chr(92) + chr(34))}" with administrator privileges'
    try:
        return subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(
            args=["osascript", "-e", script],
            returncode=124,
            stdout=str(getattr(exc, "stdout", "") or ""),
            stderr="timed out waiting for administrator authorization prompt/response",
        )


def _restart_coreaudio() -> subprocess.CompletedProcess:
    # Refresh CoreAudio device enumeration so newly installed/removed HAL drivers
    # are visible in Audio MIDI Setup and device probes without manual shell steps.
    return _run_admin("killall coreaudiod || true")


def _shell_quote_single(text: str) -> str:
    return "'" + str(text or "").replace("'", "'\\''") + "'"


def _pkg_candidates(repo_root: Path) -> list[Path]:
    out: list[Path] = []
    env = os.environ.get("WHAT_DESKTOP_AUDIO_PKG", "").strip()
    if env:
        out.append(Path(env).expanduser())
    out.append(repo_root / "assets" / "desktop-audio" / "BlackHole2ch.pkg")
    out.append(repo_root / "dist" / "assets" / "desktop-audio" / "BlackHole2ch.pkg")
    out.append(repo_root / "BlackHole2ch-0.6.0.pkg")
    unique: list[Path] = []
    seen = set()
    for item in out:
        key = str(item)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _resolve_pkg(repo_root: Path) -> Path | None:
    for candidate in _pkg_candidates(repo_root):
        if candidate.exists():
            return candidate
    return None


def get_status(repo_root: Path, receipt_path: Path, include_routing: bool = True) -> dict:
    supported = _is_mac()
    base = {
        "supported": supported,
        "installed": False,
        "installed_drivers": [],
        "managed_install": False,
        "managed_drivers": [],
        "can_auto_install": False,
        "can_auto_uninstall": False,
        "install_pkg_path": "",
        "note": "",
    }
    if not supported:
        base["note"] = "Desktop audio manager is macOS-only."
        return base

    installed = _find_installed_loopback_drivers()
    base["installed"] = len(installed) > 0
    base["installed_drivers"] = installed

    receipt = _read_json(receipt_path) or {}
    receipt_drivers = receipt.get("managed_drivers", [])
    if not isinstance(receipt_drivers, list):
        receipt_drivers = []
    managed = [x for x in receipt_drivers if x in installed]
    base["managed_drivers"] = managed
    base["managed_install"] = bool(receipt.get("installed_by_controller")) and bool(managed)
    base["can_auto_uninstall"] = bool(base["managed_install"])

    pkg = _resolve_pkg(repo_root)
    if pkg is not None:
        base["install_pkg_path"] = str(pkg)
        base["can_auto_install"] = True
    else:
        base["note"] = "No desktop audio package found in assets/dist or WHAT_DESKTOP_AUDIO_PKG."

    if base["installed"] and not base["managed_install"]:
        base["note"] = "Loopback driver exists but unmanaged by controller; auto-uninstall disabled."

    if include_routing:
        base["routing"] = audio_routing_manager.probe_routing(state_dir=receipt_path.parent)
        routing = base.get("routing", {}) if isinstance(base.get("routing"), dict) else {}
        target_output = str(routing.get("target_output") or "").strip().lower()
        current_output = str(routing.get("current_output") or "").strip().lower()
        expected = str(routing.get("name_expected") or "what-desktop").strip().lower()
        routing_managed_present = bool(expected and (target_output == expected or current_output == expected))
        if routing_managed_present and routing.get("enabled", False):
            # Allow uninstall/cleanup action to remove managed routing artifacts
            # (for example lingering what-desktop aggregate) even if driver is gone.
            base["can_auto_uninstall"] = True
            if not base["managed_install"] and not base["installed"]:
                base["note"] = "Loopback driver is not installed, but managed routing output is present."
    return base


def install(repo_root: Path, receipt_path: Path, configure_routing: bool = True) -> dict:
    status = get_status(repo_root, receipt_path)
    if not status["supported"]:
        return {"ok": False, "error": "unsupported_platform", "status": status}
    return install_action(
        repo_root=repo_root,
        receipt_path=receipt_path,
        configure_routing=bool(configure_routing),
        status=status,
        get_status=get_status,
        is_known_loopback_driver=_is_known_loopback_driver,
        find_installed_loopback_drivers=_find_installed_loopback_drivers,
        shell_quote_single=_shell_quote_single,
        run_admin=_run_admin,
        write_json=_write_json,
        ensure_routing=audio_routing_manager.ensure_routing,
        restart_coreaudio=_restart_coreaudio,
    )


def uninstall(repo_root: Path, receipt_path: Path) -> dict:
    status = get_status(repo_root, receipt_path)
    if not status["supported"]:
        return {"ok": False, "error": "unsupported_platform", "status": status}
    return uninstall_action(
        repo_root=repo_root,
        receipt_path=receipt_path,
        status=status,
        get_status=get_status,
        hal_dir=HAL_DIR,
        is_known_loopback_driver=_is_known_loopback_driver,
        shell_quote_single=_shell_quote_single,
        run_admin=_run_admin,
        remove_managed_routing=audio_routing_manager.remove_managed_routing,
    )


def warmup_admin() -> dict:
    if not _is_mac():
        return {"ok": False, "error": "unsupported_platform"}
    result = _run_admin("true")
    return {
        "ok": bool(result.returncode == 0),
        "code": int(result.returncode),
        "stdout": str(result.stdout or ""),
        "stderr": str(result.stderr or ""),
    }
