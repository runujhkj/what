from __future__ import annotations

import time
from pathlib import Path


def _passthrough_keys(payload: dict, out: dict) -> dict:
    for key in ("stderr", "stdout", "detail", "exit_code", "code", "aggregate"):
        if key in payload:
            out[key] = payload.get(key)
    return out


def ensure_coreaudio(
    *,
    state_dir: Path,
    state: dict,
    coreaudio_helper_path,
    coreaudio_prewarm_helper,
    run_coreaudio_helper,
    coreaudio_action_timeout_s,
    coreaudio_retry_on_timeout,
    coreaudio_retry_timeout_s,
) -> dict:
    helper = coreaudio_helper_path()
    if not helper:
        return {"ok": False, "error": "missing_coreaudio_helper", "routing": state}
    coreaudio_prewarm_helper(helper, state_dir)
    payload = run_coreaudio_helper(
        helper,
        "ensure",
        state_dir=state_dir,
        timeout_s=coreaudio_action_timeout_s(default=35.0),
    )
    if payload.get("error") == "coreaudio_helper_timeout" and coreaudio_retry_on_timeout():
        payload = run_coreaudio_helper(
            helper,
            "ensure",
            state_dir=state_dir,
            timeout_s=coreaudio_retry_timeout_s(),
        )
    routing = payload.get("routing", state)
    if not isinstance(routing, dict):
        routing = state
    out = {
        "ok": bool(payload.get("ok", False)),
        "error": payload.get("error", ""),
        "changed": bool(payload.get("changed", False)),
        "routing": routing,
    }
    return _passthrough_keys(payload, out)


def remove_coreaudio(
    *,
    state_dir: Path,
    state: dict,
    coreaudio_helper_path,
    run_coreaudio_helper,
    coreaudio_action_timeout_s,
) -> dict:
    helper = coreaudio_helper_path()
    if not helper:
        return {"ok": False, "error": "missing_coreaudio_helper", "routing": state}
    payload = run_coreaudio_helper(
        helper,
        "remove-managed",
        state_dir=state_dir,
        timeout_s=coreaudio_action_timeout_s(),
    )
    routing = payload.get("routing", state)
    if not isinstance(routing, dict):
        routing = state
    out = {
        "ok": bool(payload.get("ok", False)),
        "error": payload.get("error", ""),
        "changed": bool(payload.get("changed", False)),
        "routing": routing,
    }
    return _passthrough_keys(payload, out)


def ensure_switch(
    *,
    state_dir: Path,
    state: dict,
    run_switch,
    write_json,
    routing_receipt_path,
    probe_routing,
) -> dict:
    if not state.get("target_output"):
        return {"ok": False, "error": "missing_target_output", "routing": state}
    if state.get("ready", False):
        return {"ok": True, "changed": False, "routing": state}

    manager_path = str(state.get("manager_path") or "")
    target = str(state.get("target_output") or "")
    current = str(state.get("current_output") or "")
    result = run_switch(manager_path, ["-s", target, "-t", "output"])
    if result.returncode != 0:
        failed = probe_routing(state_dir=state_dir)
        return {
            "ok": False,
            "error": "route_failed",
            "code": int(result.returncode),
            "stdout": str(result.stdout or ""),
            "stderr": str(result.stderr or ""),
            "routing": failed,
        }
    write_json(
        routing_receipt_path(state_dir),
        {
            "version": 1,
            "mode": "output_switch",
            "previous_output": current,
            "routed_output": target,
            "manager": "switchaudiosource",
            "manager_path": manager_path,
            "applied_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        },
    )
    updated = probe_routing(state_dir=state_dir)
    return {"ok": True, "changed": True, "routing": updated}


def remove_switch(
    *,
    state_dir: Path,
    state: dict,
    read_json,
    run_switch,
    routing_receipt_path,
    probe_routing,
) -> dict:
    receipt_path = routing_receipt_path(state_dir)
    receipt = read_json(receipt_path) or {}
    previous = str(receipt.get("previous_output") or "").strip()
    if not previous:
        try:
            receipt_path.unlink(missing_ok=True)
        except Exception:
            pass
        return {"ok": True, "changed": False, "routing": probe_routing(state_dir=state_dir)}

    manager_path = str(state.get("manager_path") or "")
    if not manager_path:
        return {"ok": False, "error": "missing_manager", "routing": state}
    result = run_switch(manager_path, ["-s", previous, "-t", "output"])
    if result.returncode != 0:
        return {
            "ok": False,
            "error": "restore_failed",
            "code": int(result.returncode),
            "stdout": str(result.stdout or ""),
            "stderr": str(result.stderr or ""),
            "routing": probe_routing(state_dir=state_dir),
        }
    try:
        receipt_path.unlink(missing_ok=True)
    except Exception:
        pass
    return {"ok": True, "changed": True, "routing": probe_routing(state_dir=state_dir)}

