import json
import os
import subprocess
import sys
from pathlib import Path
from .audio_routing_contracts import (
    coreaudio_missing_helper_status,
    coreaudio_probe_timeout_status,
    routing_disabled_status,
    switch_missing_manager_status,
    unsupported_platform_status,
)
from .audio_routing_backend_registry import (
    AdapterContext,
    resolve_backend_adapter,
)

ROUTING_RECEIPT_FILE = "desktop-audio-routing-receipt.json"
EXPECTED_TARGET_NAME = "what-desktop"
FALLBACK_TARGET_PATTERN = "blackhole"
DEFAULT_BACKEND = "coreaudio_aggregate"
SUPPORTED_BACKENDS = {"switchaudiosource", "coreaudio_aggregate"}


def _is_mac() -> bool:
    return sys.platform == "darwin"


def _platform_name() -> str:
    return str(sys.platform or "").strip().lower()


def routing_enabled() -> bool:
    raw = os.environ.get("WHAT_DESKTOP_ROUTING_ENABLE", "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    # Default-on for macOS so desktop setup works out of the box without
    # requiring shell env wiring.
    return _is_mac()


def backend_name() -> str:
    raw = os.environ.get("WHAT_DESKTOP_ROUTING_BACKEND", DEFAULT_BACKEND).strip().lower()
    if raw in SUPPORTED_BACKENDS:
        return raw
    return DEFAULT_BACKEND


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _routing_receipt_path(state_dir: Path) -> Path:
    return state_dir / ROUTING_RECEIPT_FILE


def _find_switch_audio_source() -> str:
    candidates = [
        "/opt/homebrew/bin/SwitchAudioSource",
        "/usr/local/bin/SwitchAudioSource",
        "/usr/bin/SwitchAudioSource",
    ]
    for p in candidates:
        if Path(p).exists():
            return p
    try:
        out = subprocess.run(
            ["sh", "-lc", "command -v SwitchAudioSource || true"],
            capture_output=True,
            text=True,
        )
        path = str(out.stdout or "").strip()
        return path
    except Exception:
        return ""


def _run_switch(bin_path: str, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([bin_path, *args], capture_output=True, text=True)


def _list_outputs(bin_path: str) -> list[str]:
    result = _run_switch(bin_path, ["-a", "-t", "output"])
    if result.returncode != 0:
        return []
    return [
        line.strip()
        for line in str(result.stdout or "").splitlines()
        if line.strip()
    ]


def _current_output(bin_path: str) -> str:
    result = _run_switch(bin_path, ["-c", "-t", "output"])
    if result.returncode != 0:
        return ""
    return str(result.stdout or "").strip()


def _choose_target_output(outputs: list[str]) -> str:
    names = [str(x or "") for x in outputs]
    for name in names:
        if name.lower() == EXPECTED_TARGET_NAME.lower():
            return name
    # Legacy/manual aliases (for example "what-d") are acceptable managed targets.
    for name in names:
        low = name.lower()
        if low.startswith("what-"):
            return name
    for name in names:
        if FALLBACK_TARGET_PATTERN in name.lower():
            return name
    return ""


def _coreaudio_helper_path() -> str:
    env = os.environ.get("WHAT_COREAUDIO_HELPER", "").strip()
    if env and Path(env).exists():
        # Guard against command-mismatch helper targets.
        # CoreAudio routing backend must invoke what-coreaudio-routing.
        if Path(env).name == "what-coreaudio-aggregate":
            env = ""
        if Path(env).name == "what-coreaudio-routing":
            return env
    if env:
        # Keep explicit but incompatible override visible to caller as missing helper.
        return ""
    repo_helper = Path(__file__).resolve().parents[2] / "bin" / "what-coreaudio-routing"
    if repo_helper.exists():
        return str(repo_helper)
    return ""


def _run_coreaudio_helper(
    helper_path: str,
    command: str,
    state_dir: Path,
    expected_name: str = EXPECTED_TARGET_NAME,
    fallback_pattern: str = FALLBACK_TARGET_PATTERN,
    timeout_s: float = 90.0,
) -> dict:
    try:
        result = subprocess.run(
            [
                helper_path,
                command,
                "--state-dir",
                str(state_dir),
                "--name",
                expected_name,
                "--fallback-pattern",
                fallback_pattern,
            ],
            capture_output=True,
            text=True,
            timeout=max(0.5, float(timeout_s)),
        )
    except Exception as exc:
        if isinstance(exc, subprocess.TimeoutExpired):
            return {
                "ok": False,
                "error": "coreaudio_helper_timeout",
                "detail": "timed out waiting for coreaudio helper",
            }
        return {"ok": False, "error": "coreaudio_helper_exec_failed", "detail": str(exc)}
    out = str(result.stdout or "").strip()
    err = str(result.stderr or "").strip()
    payload = {}
    if out:
        # Accept either pure-JSON stdout or mixed logs where JSON is on the last line.
        candidates = [out]
        lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
        if lines:
            candidates.append(lines[-1])
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    payload = parsed
                    break
            except Exception:
                continue
    if not payload:
        payload = {
            "ok": result.returncode == 0,
            "error": "coreaudio_helper_invalid_output",
            "stdout": out,
            "stderr": err,
            "exit_code": int(result.returncode),
        }
    if payload.get("error") == "invalid_command":
        payload["error"] = "coreaudio_helper_command_mismatch"
        payload["detail"] = (
            f"helper '{helper_path}' rejected command '{command}'. "
            "Expected what-coreaudio-routing helper."
        )
    return payload


def _coreaudio_action_timeout_s(default: float = 20.0) -> float:
    raw = os.environ.get("WHAT_COREAUDIO_HELPER_TIMEOUT_SEC", "").strip()
    if not raw:
        return default
    try:
        val = float(raw)
    except Exception:
        return default
    return max(1.0, min(120.0, val))


def _coreaudio_retry_timeout_s(default: float = 75.0) -> float:
    raw = os.environ.get("WHAT_COREAUDIO_HELPER_RETRY_TIMEOUT_SEC", "").strip()
    if not raw:
        return default
    try:
        val = float(raw)
    except Exception:
        return default
    return max(1.0, min(180.0, val))


def _coreaudio_retry_on_timeout(default: bool = True) -> bool:
    raw = os.environ.get("WHAT_COREAUDIO_HELPER_RETRY_ON_TIMEOUT", "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _coreaudio_warmup_timeout_s(default: float = 15.0) -> float:
    raw = os.environ.get("WHAT_COREAUDIO_HELPER_WARMUP_TIMEOUT_SEC", "").strip()
    if not raw:
        return default
    try:
        val = float(raw)
    except Exception:
        return default
    return max(0.5, min(30.0, val))


def _coreaudio_prewarm_helper(helper: str, state_dir: Path) -> dict:
    # Best-effort warmup to absorb first-run helper startup/compile latency
    # before the mutating ensure/remove actions.
    return _run_coreaudio_helper(
        helper,
        "probe",
        state_dir=state_dir,
        timeout_s=_coreaudio_warmup_timeout_s(),
    )


def _coreaudio_backend_probe(state_dir: Path, receipt: dict) -> dict:
    helper = _coreaudio_helper_path()
    if not helper:
        return coreaudio_missing_helper_status(
            expected_name=EXPECTED_TARGET_NAME,
            helper_path=helper,
            can_restore=bool(receipt.get("previous_output")),
        )
    # Probe should never stall /control/status; keep this fast.
    payload = _run_coreaudio_helper(helper, "probe", state_dir=state_dir, timeout_s=1.5)
    if payload.get("error") == "coreaudio_helper_timeout":
        return coreaudio_probe_timeout_status(
            helper_path=helper,
            can_restore=bool(receipt.get("previous_output")),
        )
    routing = payload.get("routing", {})
    if not isinstance(routing, dict):
        routing = {}
    routing.setdefault("backend", "coreaudio_aggregate")
    routing.setdefault("manager", "coreaudio_aggregate")
    # Always use the routing helper path here. Helper payload may include
    # aggregate-helper details, which are not valid command targets for
    # ensure/remove-managed calls.
    routing["manager_path"] = helper
    routing.setdefault("name_expected", EXPECTED_TARGET_NAME)
    routing.setdefault("supported", True)
    routing.setdefault("enabled", True)
    routing.setdefault("manual_steps", [])
    routing.setdefault("blockers", [])
    return routing


def _switch_backend_probe(state_dir: Path, receipt: dict) -> dict:
    _ = state_dir
    manager = _find_switch_audio_source()
    if not manager:
        return switch_missing_manager_status(
            expected_name=EXPECTED_TARGET_NAME,
            can_restore=bool(receipt.get("previous_output")),
        )
    outputs = _list_outputs(manager)
    current = _current_output(manager)
    target = _choose_target_output(outputs)
    ready = bool(target and current and current.lower() == target.lower())
    target_is_expected = bool(
        target and (
            target.lower() == EXPECTED_TARGET_NAME.lower()
            or target.lower().startswith("what-")
        )
    )
    note = ""
    manual_steps: list[str] = []
    blockers: list[str] = []
    if not target:
        note = "No routable desktop target found."
        blockers.append("missing_target_output")
        manual_steps = [
            "Create 'what-desktop' in Audio MIDI Setup, or ensure BlackHole output is present.",
            "Then rerun desktop setup.",
        ]
    elif not target_is_expected:
        note = "Using BlackHole fallback; create 'what-desktop' for preferred routing."
        manual_steps = [
            "Create a Multi-Output Device in Audio MIDI Setup named 'what-desktop'.",
            "Include your listening output and loopback output, then rerun setup.",
        ]
    elif target and target.lower() != EXPECTED_TARGET_NAME.lower():
        note = f"Using legacy what-* target ({target}); optional: recreate as 'what-desktop' for consistency."
    return {
        "supported": True,
        "enabled": True,
        "ready": ready,
        "changed": False,
        "name_expected": EXPECTED_TARGET_NAME,
        "note": note,
        "manual_steps": manual_steps,
        "manager": "switchaudiosource",
        "manager_path": manager,
        "current_output": current,
        "target_output": target,
        "target_is_expected": target_is_expected,
        "can_route": True,
        "can_restore": bool(receipt.get("previous_output")),
        "backend": "switchaudiosource",
        "blockers": blockers,
    }


def probe_routing(state_dir: Path | None = None) -> dict:
    state_dir = state_dir or Path.home() / ".what"
    receipt = _read_json(_routing_receipt_path(state_dir)) or {}
    platform = "darwin" if _is_mac() else _platform_name()
    if platform != "darwin":
        return unsupported_platform_status(
            enabled=routing_enabled(),
            backend=backend_name(),
            expected_name=EXPECTED_TARGET_NAME,
        )
    if not routing_enabled():
        return routing_disabled_status(backend=backend_name(), expected_name=EXPECTED_TARGET_NAME)
    backend = backend_name()
    ctx = AdapterContext(
        expected_target_name=EXPECTED_TARGET_NAME,
        fallback_target_pattern=FALLBACK_TARGET_PATTERN,
        coreaudio_probe=_coreaudio_backend_probe,
        switch_probe=_switch_backend_probe,
        coreaudio_helper_path=_coreaudio_helper_path,
        coreaudio_prewarm_helper=_coreaudio_prewarm_helper,
        run_coreaudio_helper=_run_coreaudio_helper,
        coreaudio_action_timeout_s=_coreaudio_action_timeout_s,
        coreaudio_retry_on_timeout=_coreaudio_retry_on_timeout,
        coreaudio_retry_timeout_s=_coreaudio_retry_timeout_s,
        run_switch=_run_switch,
        read_json=_read_json,
        write_json=_write_json,
        routing_receipt_path=_routing_receipt_path,
        probe_routing=probe_routing,
    )
    adapter = resolve_backend_adapter(platform=platform, backend_name=backend, ctx=ctx)
    return adapter.probe(state_dir=state_dir, receipt=receipt)


def ensure_routing(repo_root: Path, state_dir: Path | None = None) -> dict:
    _ = repo_root
    state_dir = state_dir or Path.home() / ".what"
    state = probe_routing(state_dir=state_dir)
    if not state.get("supported", False):
        return {"ok": False, "error": "unsupported_platform", "routing": state}
    if not state.get("enabled", False):
        return {"ok": True, "changed": False, "routing": state}
    if not state.get("can_route", False):
        blockers = state.get("blockers", [])
        err = blockers[0] if blockers else "missing_manager"
        return {"ok": False, "error": err, "routing": state}
    platform = "darwin" if _is_mac() else _platform_name()
    ctx = AdapterContext(
        expected_target_name=EXPECTED_TARGET_NAME,
        fallback_target_pattern=FALLBACK_TARGET_PATTERN,
        coreaudio_probe=_coreaudio_backend_probe,
        switch_probe=_switch_backend_probe,
        coreaudio_helper_path=_coreaudio_helper_path,
        coreaudio_prewarm_helper=_coreaudio_prewarm_helper,
        run_coreaudio_helper=_run_coreaudio_helper,
        coreaudio_action_timeout_s=_coreaudio_action_timeout_s,
        coreaudio_retry_on_timeout=_coreaudio_retry_on_timeout,
        coreaudio_retry_timeout_s=_coreaudio_retry_timeout_s,
        run_switch=_run_switch,
        read_json=_read_json,
        write_json=_write_json,
        routing_receipt_path=_routing_receipt_path,
        probe_routing=probe_routing,
    )
    adapter = resolve_backend_adapter(platform=platform, backend_name=str(state.get("backend") or backend_name()), ctx=ctx)
    return adapter.ensure(state_dir=state_dir, state=state)


def remove_managed_routing(repo_root: Path, state_dir: Path | None = None) -> dict:
    _ = repo_root
    state_dir = state_dir or Path.home() / ".what"
    state = probe_routing(state_dir=state_dir)
    if not state.get("supported", False):
        return {"ok": False, "error": "unsupported_platform", "routing": state}
    if not state.get("enabled", False):
        return {"ok": True, "changed": False, "routing": state}
    platform = "darwin" if _is_mac() else _platform_name()
    ctx = AdapterContext(
        expected_target_name=EXPECTED_TARGET_NAME,
        fallback_target_pattern=FALLBACK_TARGET_PATTERN,
        coreaudio_probe=_coreaudio_backend_probe,
        switch_probe=_switch_backend_probe,
        coreaudio_helper_path=_coreaudio_helper_path,
        coreaudio_prewarm_helper=_coreaudio_prewarm_helper,
        run_coreaudio_helper=_run_coreaudio_helper,
        coreaudio_action_timeout_s=_coreaudio_action_timeout_s,
        coreaudio_retry_on_timeout=_coreaudio_retry_on_timeout,
        coreaudio_retry_timeout_s=_coreaudio_retry_timeout_s,
        run_switch=_run_switch,
        read_json=_read_json,
        write_json=_write_json,
        routing_receipt_path=_routing_receipt_path,
        probe_routing=probe_routing,
    )
    adapter = resolve_backend_adapter(platform=platform, backend_name=str(state.get("backend") or backend_name()), ctx=ctx)
    return adapter.remove(state_dir=state_dir, state=state)
