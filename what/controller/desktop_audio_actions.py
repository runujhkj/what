from __future__ import annotations

import os
import time
from pathlib import Path


def _routing_context(routing_result: dict) -> tuple[bool, dict, list[str]]:
    routing_ok = bool(routing_result.get("ok", False))
    routing_state = routing_result.get("routing", {})
    manual_steps = list(routing_state.get("manual_steps", [])) if isinstance(routing_state, dict) else []
    return routing_ok, routing_state, manual_steps


def _is_missing_target(routing_result: dict) -> bool:
    return str((routing_result or {}).get("error") or "").strip().lower() == "missing_target_output"


def _resolve_routing_with_retries(
    *,
    configure_routing: bool,
    ensure_routing,
    repo_root: Path,
    state_dir: Path,
    initial_result: dict,
    restart_coreaudio,
) -> tuple[dict, bool, dict]:
    result = initial_result if isinstance(initial_result, dict) else {}
    restarted = False
    restart_diag: dict = {}
    if not configure_routing or result.get("ok") or not _is_missing_target(result):
        return result, restarted, restart_diag

    attempts_raw = os.environ.get("WHAT_DESKTOP_ROUTE_RETRY_ATTEMPTS", "").strip()
    delay_raw = os.environ.get("WHAT_DESKTOP_ROUTE_RETRY_DELAY_SEC", "").strip()
    restart_on_missing_raw = os.environ.get("WHAT_DESKTOP_RESTART_COREAUDIO_ON_MISSING_TARGET", "").strip().lower()
    try:
        attempts = max(0, min(6, int(attempts_raw))) if attempts_raw else 3
    except Exception:
        attempts = 3
    try:
        delay_s = max(0.1, min(3.0, float(delay_raw))) if delay_raw else 0.75
    except Exception:
        delay_s = 0.75
    restart_on_missing = restart_on_missing_raw not in {"0", "false", "no", "off"}

    for _ in range(attempts):
        time.sleep(delay_s)
        retry = ensure_routing(repo_root, state_dir=state_dir)
        if isinstance(retry, dict):
            result = retry
        if result.get("ok") or not _is_missing_target(result):
            return result, restarted, restart_diag

    if restart_on_missing and callable(restart_coreaudio):
        try:
            proc = restart_coreaudio()
            code = int(getattr(proc, "returncode", 1))
            restarted = code == 0
            restart_diag = {
                "code": code,
                "stdout": str(getattr(proc, "stdout", "") or ""),
                "stderr": str(getattr(proc, "stderr", "") or ""),
            }
            if restarted:
                time.sleep(1.25)
                retry = ensure_routing(repo_root, state_dir=state_dir)
                if isinstance(retry, dict):
                    result = retry
        except Exception as exc:
            restart_diag = {"code": -1, "stderr": str(exc)}
    return result, restarted, restart_diag


def install_action(
    *,
    repo_root: Path,
    receipt_path: Path,
    configure_routing: bool,
    status: dict,
    get_status,
    is_known_loopback_driver,
    find_installed_loopback_drivers,
    shell_quote_single,
    run_admin,
    write_json,
    ensure_routing,
    restart_coreaudio=None,
) -> dict:
    if status["managed_install"]:
        routing_result = (
            ensure_routing(repo_root, state_dir=receipt_path.parent)
            if configure_routing
            else {"ok": True, "changed": False, "routing": status.get("routing", {})}
        )
        routing_result, restarted, restart_diag = _resolve_routing_with_retries(
            configure_routing=bool(configure_routing),
            ensure_routing=ensure_routing,
            repo_root=repo_root,
            state_dir=receipt_path.parent,
            initial_result=routing_result,
            restart_coreaudio=restart_coreaudio,
        )
        routing_ok, routing_state, manual_steps = _routing_context(routing_result)
        return {
            "ok": True,
            "changed": bool(routing_result.get("changed", False)),
            "coreaudio_restarted": bool(restarted),
            "coreaudio_restart_detail": restart_diag,
            "configure_routing": bool(configure_routing),
            "routing_ok": routing_ok,
            "routing_error": "" if routing_ok else str(routing_result.get("error", "routing_failed")),
            "routing_detail": routing_result if not routing_ok else {},
            "manual_steps": manual_steps,
            "routing": routing_state,
            "routing_changed": bool(routing_result.get("changed", False)),
            "status": get_status(repo_root, receipt_path),
        }
    if status["installed"] and not status["managed_install"]:
        installed = [x for x in status.get("installed_drivers", []) if is_known_loopback_driver(x)]
        if not installed:
            return {"ok": False, "error": "unmanaged_existing_install", "status": status}
        routing_result = (
            ensure_routing(repo_root, state_dir=receipt_path.parent)
            if configure_routing
            else {"ok": True, "changed": False, "routing": status.get("routing", {})}
        )
        routing_result, restarted, restart_diag = _resolve_routing_with_retries(
            configure_routing=bool(configure_routing),
            ensure_routing=ensure_routing,
            repo_root=repo_root,
            state_dir=receipt_path.parent,
            initial_result=routing_result,
            restart_coreaudio=restart_coreaudio,
        )
        write_json(
            receipt_path,
            {
                "version": 1,
                "installed_by_controller": True,
                "managed_drivers": installed,
                "pkg_path": status.get("install_pkg_path", ""),
                "adopted_existing_install": True,
            },
        )
        routing_ok, routing_state, manual_steps = _routing_context(routing_result)
        return {
            "ok": True,
            "changed": False,
            "adopted_existing_install": True,
            "coreaudio_restarted": bool(restarted),
            "coreaudio_restart_detail": restart_diag,
            "configure_routing": bool(configure_routing),
            "routing_ok": routing_ok,
            "routing_error": "" if routing_ok else str(routing_result.get("error", "routing_failed")),
            "routing_detail": routing_result if not routing_ok else {},
            "manual_steps": manual_steps,
            "routing": routing_state,
            "routing_changed": bool(routing_result.get("changed", False)),
            "status": get_status(repo_root, receipt_path),
        }
    pkg = status.get("install_pkg_path", "")
    if not pkg:
        return {"ok": False, "error": "missing_pkg", "status": status}

    before = find_installed_loopback_drivers()
    # Avoid forcibly restarting coreaudiod during install. It can interrupt
    # active playback and cause transient hangs in System Settings on some macOS versions.
    cmd = f"installer -pkg {shell_quote_single(pkg)} -target /"
    result = run_admin(cmd)
    after = find_installed_loopback_drivers()
    new = [x for x in after if x not in before]
    managed = [x for x in (new or after) if is_known_loopback_driver(x)]
    if result.returncode == 0 and managed:
        routing_result = (
            ensure_routing(repo_root, state_dir=receipt_path.parent)
            if configure_routing
            else {"ok": True, "changed": False, "routing": status.get("routing", {})}
        )
        routing_result, restarted, restart_diag = _resolve_routing_with_retries(
            configure_routing=bool(configure_routing),
            ensure_routing=ensure_routing,
            repo_root=repo_root,
            state_dir=receipt_path.parent,
            initial_result=routing_result,
            restart_coreaudio=restart_coreaudio,
        )
        write_json(
            receipt_path,
            {
                "version": 1,
                "installed_by_controller": True,
                "managed_drivers": managed,
                "pkg_path": pkg,
            },
        )
        routing_ok, routing_state, manual_steps = _routing_context(routing_result)
        return {
            "ok": True,
            "changed": True,
            "coreaudio_restarted": bool(restarted),
            "coreaudio_restart_detail": restart_diag,
            "configure_routing": bool(configure_routing),
            "routing_ok": routing_ok,
            "routing_error": "" if routing_ok else str(routing_result.get("error", "routing_failed")),
            "routing_detail": routing_result if not routing_ok else {},
            "manual_steps": manual_steps,
            "routing": routing_state,
            "routing_changed": bool(routing_result.get("changed", False)),
            "status": get_status(repo_root, receipt_path),
        }
    return {
        "ok": False,
        "error": "install_failed",
        "code": int(result.returncode),
        "stdout": str(result.stdout or ""),
        "stderr": str(result.stderr or ""),
        "status": get_status(repo_root, receipt_path),
    }


def uninstall_action(
    *,
    repo_root: Path,
    receipt_path: Path,
    status: dict,
    get_status,
    hal_dir: Path,
    is_known_loopback_driver,
    shell_quote_single,
    run_admin,
    remove_managed_routing,
) -> dict:
    if not status["managed_install"]:
        routing_result = remove_managed_routing(repo_root, state_dir=receipt_path.parent)
        try:
            receipt_path.unlink(missing_ok=True)
        except Exception:
            pass
        routing_ok, routing_state, manual_steps = _routing_context(routing_result)
        if routing_ok:
            return {
                "ok": True,
                "changed": bool(routing_result.get("changed", False)),
                "routing_ok": True,
                "routing_error": "",
                "routing_detail": {},
                "manual_steps": manual_steps,
                "routing": routing_state,
                "routing_changed": bool(routing_result.get("changed", False)),
                "status": get_status(repo_root, receipt_path),
            }
        routed_err = str(routing_result.get("error") or "").strip()
        top_error = routed_err or "unmanaged_install"
        return {
            "ok": False,
            "error": top_error,
            "routing_ok": False,
            "routing_error": routed_err or "routing_restore_failed",
            "routing_detail": routing_result,
            "manual_steps": manual_steps,
            "routing": routing_state,
            "status": get_status(repo_root, receipt_path),
        }
    managed = status.get("managed_drivers", [])
    if not managed:
        try:
            receipt_path.unlink(missing_ok=True)
        except Exception:
            pass
        return {"ok": True, "changed": False, "status": get_status(repo_root, receipt_path)}

    targets = [str(hal_dir / name) for name in managed if is_known_loopback_driver(name)]
    if not targets:
        try:
            receipt_path.unlink(missing_ok=True)
        except Exception:
            pass
        return {"ok": True, "changed": False, "status": get_status(repo_root, receipt_path)}

    quoted = " ".join([shell_quote_single(x) for x in targets])
    # Avoid forcibly restarting coreaudiod on uninstall; that has caused
    # intermittent System Settings hangs on some macOS versions.
    result = run_admin(f"rm -rf {quoted}")
    if result.returncode == 0:
        routing_result = remove_managed_routing(repo_root, state_dir=receipt_path.parent)
        try:
            receipt_path.unlink(missing_ok=True)
        except Exception:
            pass
        routing_ok, routing_state, manual_steps = _routing_context(routing_result)
        return {
            "ok": True,
            "changed": True,
            "coreaudio_restarted": False,
            "routing_ok": routing_ok,
            "routing_error": "" if routing_ok else str(routing_result.get("error", "routing_restore_failed")),
            "routing_detail": routing_result if not routing_ok else {},
            "manual_steps": manual_steps,
            "routing": routing_state,
            "routing_changed": bool(routing_result.get("changed", False)),
            "status": get_status(repo_root, receipt_path),
        }
    return {
        "ok": False,
        "error": "uninstall_failed",
        "code": int(result.returncode),
        "stdout": str(result.stdout or ""),
        "stderr": str(result.stderr or ""),
        "status": get_status(repo_root, receipt_path),
    }
