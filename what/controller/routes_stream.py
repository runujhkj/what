import re
import time
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, Request

from ..desktop_audio import (
    default_desktop_backend,
    default_mic_backend,
    list_desktop_devices,
    normalize_desktop_backend,
)
from ..live_audio_probe import measure_live_source
from .desktop_source_authority import parse_desktop_device_rows, resolve_desktop_roles
from .desktop_capture_state_machine import (
    DesktopProbeSnapshot,
    classify_probe,
    should_retry_single_candidate,
    should_switch_candidate,
)
from . import audio_routing_manager
from . import native_desktop_helper_manager
from .state import StreamSettings
from .native_desktop_backend import native_helper_capabilities, desktop_source_backend


_DESKTOP_TEST_PING_SOUND_CANDIDATES = (
    "/System/Library/Sounds/Ping.aiff",
    "/System/Library/Sounds/Glass.aiff",
    "/System/Library/Sounds/Tink.aiff",
)


def _emit_desktop_start_ping() -> dict[str, object]:
    if str(os.environ.get("WHAT_DESKTOP_START_PING_ENABLE", "1")).strip().lower() in {
        "0",
        "false",
        "off",
        "no",
    }:
        return {"ok": False, "error": "disabled"}
    afplay = shutil.which("afplay")
    if not afplay:
        return {"ok": False, "error": "afplay_not_found"}
    sound_path = ""
    for cand in _DESKTOP_TEST_PING_SOUND_CANDIDATES:
        if Path(cand).exists():
            sound_path = cand
            break
    if not sound_path:
        return {"ok": False, "error": "sound_not_found"}
    try:
        proc = subprocess.Popen(
            [afplay, sound_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
        )
        return {"ok": True, "pid": int(proc.pid), "sound": sound_path}
    except Exception as exc:
        return {"ok": False, "error": "launch_failed", "detail": str(exc)}


def _parse_device_selector(raw: str | None) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    if text.startswith(":"):
        return text
    match = re.match(r"^\s*(\d+)\s*:", text)
    if match:
        return f":{match.group(1)}"
    return text


def _device_rows_for_backend(backend: str | None) -> list[str]:
    selected = normalize_desktop_backend(backend or default_desktop_backend())
    try:
        devices = list_desktop_devices(selected)
    except Exception:
        return []
    return [str(x or "").strip() for x in (devices or []) if str(x or "").strip()]


def _is_capture_candidate_label(label: str) -> bool:
    low = str(label or "").strip().lower()
    if not low:
        return False
    if "what-desktop" in low or low.startswith("what-"):
        return True
    return (
        "blackhole" in low
        or "loopback" in low
        or "soundflower" in low
        or "vb-cable" in low
    )


def _selector_label(rows: list[str], selector: str) -> str:
    target = _parse_device_selector(selector)
    if not target:
        return ""
    for row in rows:
        parsed = _parse_device_selector(row)
        if parsed == target:
            return row
    return ""


def _selector_for_output_target(rows: list[str], output_target: str | None) -> str:
    target = str(output_target or "").strip().lower()
    if not target:
        return ""
    parsed = _parse_device_selector(target)
    if parsed.startswith(":"):
        return parsed
    for row in rows:
        sel = _parse_device_selector(row)
        if not sel:
            continue
        label = str(_selector_label(rows, sel) or "").strip().lower()
        if not label:
            continue
        if (
            label == target
            or label.endswith(f": {target}")
            or (f":{target}" in label)
            or (target in label)
        ):
            return sel
    return ""


def _preferred_native_helper_capture_selector(
    rows: list[str],
    *,
    output_target: str | None,
    current_selector: str | None,
) -> str:
    parsed = parse_desktop_device_rows(rows)
    out_sel = _selector_for_output_target(rows, output_target)
    cur_sel = _parse_device_selector(current_selector)
    by_sel = {row.selector: row for row in parsed}

    # If current selector is a valid loopback/capture selector, keep it.
    cur_row = by_sel.get(cur_sel)
    if cur_row and (not cur_row.is_mic_like) and cur_row.is_loopback_like:
        return cur_row.selector

    # Prefer an explicit loopback selector (e.g. BlackHole) over routed output
    # selector (what-desktop) for helper-side capture.
    for row in parsed:
        if row.is_mic_like:
            continue
        if out_sel and row.selector == out_sel:
            continue
        if row.is_loopback_like:
            return row.selector

    # Fallback to current/output when no loopback selector exists.
    if cur_row and not cur_row.is_mic_like:
        return cur_row.selector
    if out_sel:
        return out_sel
    return cur_sel


def _capture_candidates(
    rows: list[str],
    *,
    output_target: str | None,
    input_mode: str,
) -> list[str]:
    candidates = _desktop_device_candidates(rows)
    candidates = _desktop_candidates_for_mode(input_mode, rows, candidates)
    output_sel = _selector_for_output_target(rows, output_target)
    if output_sel:
        output_label = str(_selector_label(rows, output_sel) or "").strip().lower()
        # Keep what-* aggregate selectors available as capture candidates.
        # Excluding output target unconditionally can force desktop capture to a
        # loopback selector that reports true-zero while routed output is active.
        keep_output_as_capture = ("what-desktop" in output_label) or output_label.startswith("what-")
        if not keep_output_as_capture:
            candidates = [sel for sel in candidates if _parse_device_selector(sel) != output_sel]
    return candidates


def _desktop_candidates_for_mode(input_mode: str, rows: list[str], candidates: list[str]) -> list[str]:
    _ = input_mode
    _ = rows
    return [str(x or "").strip() for x in (candidates or []) if str(x or "").strip()]


def _desktop_capture_fallback_enabled() -> bool:
    raw = str(os.environ.get("WHAT_DESKTOP_CAPTURE_FALLBACK_ENABLE", "")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _output_route_matches_target(route: dict, output_target: str) -> bool:
    target = str(output_target or "").strip().lower()
    if not target:
        return False
    current = str(route.get("current_output") or "").strip().lower()
    preferred = str(route.get("target_output") or "").strip().lower()
    return any(val == target for val in (current, preferred) if val)


def _pick_desktop_device_selector(preferred_backend: str | None) -> str:
    rows = _device_rows_for_backend(preferred_backend)
    candidates = _desktop_device_candidates(rows)
    candidates = _desktop_candidates_for_mode("desktop", rows, candidates)
    if candidates:
        return candidates[0]
    return ""


def _desktop_device_candidates(rows: list[str]) -> list[str]:
    preferred = ("what-desktop", "what-", "blackhole", "loopback", "soundflower", "vb-cable")
    out: list[str] = []
    seen: set[str] = set()
    blocked_tokens = ("microphone", " mic", "mic ", "input")

    def _blocked_row(row: str) -> bool:
        low = str(row or "").strip().lower()
        if not low:
            return True
        return any(tok in low for tok in blocked_tokens)

    for token in preferred:
        for row in rows:
            if _blocked_row(row):
                continue
            if not _is_capture_candidate_label(row):
                continue
            if token not in row.lower():
                continue
            picked = _parse_device_selector(row)
            if not picked or picked in seen:
                continue
            seen.add(picked)
            out.append(picked)
    for row in rows:
        if _blocked_row(row):
            continue
        if not _is_capture_candidate_label(row):
            continue
        picked = _parse_device_selector(row)
        if not picked or picked in seen:
            continue
        seen.add(picked)
        out.append(picked)
    # Preserve preferred-order pass above (what-desktop/what-* first), then
    # other capture-class loopback devices.
    return out


def _mic_selector_candidates(rows: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    # Prefer explicit microphone/input labels first. If none are present,
    # fallback to any non-loopback audio selector.
    preferred_tokens = ("microphone", " mic", "mic ", "input")
    blocked_tokens = ("what-desktop", "blackhole", "loopback", "soundflower", "vb-cable")

    def _append_if_valid(row: str) -> None:
        sel = _parse_device_selector(row)
        if not sel or sel in seen:
            return
        seen.add(sel)
        out.append(sel)

    for row in rows:
        low = str(row or "").strip().lower()
        if not low:
            continue
        if any(token in low for token in preferred_tokens):
            _append_if_valid(row)

    if out:
        return out

    for row in rows:
        low = str(row or "").strip().lower()
        if not low:
            continue
        if any(token in low for token in blocked_tokens):
            continue
        _append_if_valid(row)
    return out


def _wait_for_desktop_probe_state(state, *, after_seq: int, timeout_s: float = 4.0) -> str:
    deadline = time.time() + max(0.2, float(timeout_s))
    while time.time() < deadline:
        observed = ""
        with state.stream_log_lock:
            rows = [line for seq, line in state.stream_logs if int(seq) > int(after_seq)]
        for line in rows:
            text = str(line or "").strip().lower()
            if "capture probe: desktop=" not in text:
                continue
            if "desktop=signal" in text:
                return "signal"
            if "desktop=active" in text:
                return "active"
            if "desktop=error" in text:
                return "error"
            if "desktop=silent" in text:
                observed = "silent"
        if observed:
            return observed
        time.sleep(0.08)
    return ""


def _latest_desktop_probe_detail(state, *, after_seq: int) -> tuple[int | None, int | None]:
    code: int | None = None
    byte_count: int | None = None
    with state.stream_log_lock:
        rows = [line for seq, line in state.stream_logs if int(seq) > int(after_seq)]
    for line in rows:
        text = str(line or "").strip().lower()
        if "capture probe detail:" not in text or "desktop_state=" not in text:
            continue
        match_code = re.search(r"\bcode=(-?\d+)\b", text)
        match_bytes = re.search(r"\bbytes=(\d+)\b", text)
        if match_code:
            try:
                code = int(match_code.group(1))
            except Exception:
                code = None
        if match_bytes:
            try:
                byte_count = int(match_bytes.group(1))
            except Exception:
                byte_count = None
    return code, byte_count


def _probe_desktop_candidate(backend: str, selector: str) -> dict[str, int | str]:
    input_cfg = SimpleNamespace(
        mic_backend="avfoundation",
        mic_device=":0",
        mic_enabled=False,
        desktop_backend=str(backend or ""),
        desktop_device=str(selector or ""),
        desktop_enabled=True,
    )
    audio_cfg = SimpleNamespace(channels=1, sample_rate=16000, frame_ms=30)
    try:
        measured = measure_live_source("desktop", input_cfg, audio_cfg, duration_sec=0.28)
        if isinstance(measured, dict):
            return measured
    except Exception:
        pass
    return {"state": "error", "level": -1}


def _probe_mic_candidate(backend: str, selector: str) -> dict[str, int | str]:
    input_cfg = SimpleNamespace(
        mic_backend=str(backend or "avfoundation"),
        mic_device=str(selector or ""),
        mic_enabled=True,
        desktop_backend="avfoundation",
        desktop_device=":0",
        desktop_enabled=False,
    )
    audio_cfg = SimpleNamespace(channels=1, sample_rate=16000, frame_ms=30)
    try:
        measured = measure_live_source("mic", input_cfg, audio_cfg, duration_sec=0.28)
        if isinstance(measured, dict):
            return measured
    except Exception:
        pass
    return {"state": "error", "level": -1}


def _capture_selector_from_settings(settings: StreamSettings) -> str:
    return _parse_device_selector(settings.desktop_capture_input or settings.desktop_device or "")


def _with_desktop_capture_input(settings: StreamSettings, capture_input: str | None) -> StreamSettings:
    mirrored = _parse_device_selector(capture_input or "")
    return StreamSettings(
        input_mode=settings.input_mode,
        file_path=settings.file_path,
        realtime=bool(settings.realtime),
        mic_enabled=bool(settings.mic_enabled),
        mic_backend=settings.mic_backend,
        mic_device=settings.mic_device,
        desktop_enabled=bool(settings.desktop_enabled),
        desktop_backend=settings.desktop_backend,
        desktop_device=mirrored or None,
        desktop_output_target=settings.desktop_output_target,
        desktop_capture_input=mirrored or None,
        event_prefix=settings.event_prefix,
    )


def _pick_signal_candidate(backend: str, selectors: list[str], current: str) -> str:
    best = str(current or "")
    best_score = -10_000
    for sel in selectors:
        sample = _probe_desktop_candidate(backend, sel)
        state = str(sample.get("state", "")).strip().lower()
        raw_level = sample.get("level", -1)
        level = int(raw_level if raw_level is not None else -1)
        # Prefer explicit signal, then higher measured level; error stays lowest.
        score = level
        if state == "signal":
            score += 10_000
        elif state == "silent":
            score += 0
        else:
            score -= 5_000
        if score > best_score:
            best_score = score
            best = sel
    return best


def _scan_candidate_levels(backend: str, selectors: list[str]) -> list[tuple[str, str, int]]:
    rows: list[tuple[str, str, int]] = []
    for sel in selectors:
        sample = _probe_desktop_candidate(backend, sel)
        state = str(sample.get("state", "")).strip().lower()
        raw_level = sample.get("level", -1)
        level = int(raw_level if raw_level is not None else -1)
        rows.append((sel, state, level))
    return rows


def _should_rebuild_for_true_zero(
    *,
    probe_state: str,
    detail_code: int | None,
    detail_bytes: int | None,
    scans: list[tuple[str, str, int]],
) -> bool:
    if str(probe_state or "").strip().lower() != "silent":
        return False
    if detail_code is not None and int(detail_code) != 0:
        return False
    if detail_bytes is None or int(detail_bytes) <= 0:
        return False
    if not scans:
        return False
    for _sel, state, level in scans:
        if str(state or "").strip().lower() != "silent":
            return False
        if int(level) > 0:
            return False
    return True


def _all_silent_zero_scans(scans: list[tuple[str, str, int]]) -> bool:
    if not scans:
        return False
    for _sel, state, level in scans:
        if str(state or "").strip().lower() != "silent":
            return False
        if int(level) > 0:
            return False
    return True


def _resolve_stream_defaults(settings: StreamSettings) -> tuple[StreamSettings, dict[str, str]]:
    mic_enabled = bool(settings.mic_enabled)
    desktop_enabled = bool(settings.desktop_enabled)
    notes: dict[str, str] = {}
    mic_backend = str(settings.mic_backend or "").strip()
    mic_device = str(settings.mic_device or "").strip()
    desktop_backend = normalize_desktop_backend(settings.desktop_backend or default_desktop_backend())
    legacy_desktop_device = _parse_device_selector(settings.desktop_device)
    desktop_output_target = str(settings.desktop_output_target or "").strip()
    desktop_capture_input = _parse_device_selector(settings.desktop_capture_input or legacy_desktop_device)

    if mic_enabled:
        if not mic_backend:
            mic_backend = default_mic_backend()
        if mic_backend == "avfoundation":
            rows = _device_rows_for_backend(mic_backend)
            candidates = _mic_selector_candidates(rows)
            current_sel = _parse_device_selector(mic_device)
            if not current_sel:
                mic_device = candidates[0] if candidates else ":0"
            else:
                current_valid = bool(_selector_label(rows, current_sel))
                is_mic_candidate = current_sel in set(candidates)
                if not current_valid and candidates:
                    mic_device = candidates[0]
                    notes["mic_device_reselected"] = "selector_not_present"
                elif not current_valid:
                    mic_device = ":0"
                    notes["mic_device_reselected"] = "selector_not_present_defaulted"
                elif candidates and not is_mic_candidate:
                    mic_device = candidates[0]
                    notes["mic_device_reselected"] = "non_mic_candidate"
                else:
                    mic_device = current_sel
                    if candidates:
                        sample = _probe_mic_candidate(mic_backend, mic_device)
                        state = str(sample.get("state", "")).strip().lower()
                        if state == "error":
                            replacement = ""
                            for sel in candidates:
                                probe = _probe_mic_candidate(mic_backend, sel)
                                probe_state = str(probe.get("state", "")).strip().lower()
                                if probe_state != "error":
                                    replacement = sel
                                    break
                            if replacement and replacement != mic_device:
                                mic_device = replacement
                                notes["mic_device_reselected"] = "probe_error"
        elif not mic_device:
            mic_device = ":0"

    if desktop_enabled:
        rows = _device_rows_for_backend(desktop_backend)
        resolved_output_target, resolved_capture_input = resolve_desktop_roles(
            rows,
            current_output_target=desktop_output_target,
            current_capture_input=desktop_capture_input,
            legacy_desktop_device=legacy_desktop_device,
        )
        if resolved_output_target:
            desktop_output_target = resolved_output_target
        if resolved_capture_input:
            desktop_capture_input = resolved_capture_input
        candidates = _capture_candidates(
            rows,
            output_target=desktop_output_target,
            input_mode=settings.input_mode,
        )
        current_label = _selector_label(rows, desktop_capture_input) if desktop_capture_input else ""
        current_is_candidate = bool(
            desktop_capture_input
            and current_label
            and desktop_capture_input in set(candidates)
        )
        if desktop_capture_input and not current_is_candidate:
            # Persisted selectors can drift across sessions/restarts as AVFoundation
            # indices move. Force a preferred capture-class selector for desktop capture.
            desktop_capture_input = ""
            notes["desktop_device_reselected"] = "non_capture_candidate_or_missing"
        if not desktop_capture_input:
            desktop_capture_input = (candidates[0] if candidates else "")
        # Keep desktop enabled only when we have concrete role bindings.
        if not desktop_output_target:
            desktop_enabled = False
            notes["desktop_disabled_reason"] = "no_desktop_output_target"
        elif not desktop_capture_input:
            desktop_enabled = False
            notes["desktop_disabled_reason"] = "no_desktop_capture_input"

    return StreamSettings(
        input_mode=settings.input_mode,
        file_path=settings.file_path,
        realtime=bool(settings.realtime),
        mic_enabled=mic_enabled,
        mic_backend=mic_backend or None,
        mic_device=mic_device or None,
        desktop_enabled=desktop_enabled,
        desktop_backend=desktop_backend or None,
        desktop_device=desktop_capture_input or None,
        desktop_output_target=(desktop_output_target or None),
        desktop_capture_input=desktop_capture_input or None,
        event_prefix=settings.event_prefix,
    ), notes


def register_stream_routes(
    app: FastAPI,
    cfg,
    state,
    *,
    repo_root,
    desktop_audio_manager_mod,
    desktop_audio_receipt_path,
    process_running_fn,
    start_service_fn,
    start_client_fn,
    stop_client_fn,
    read_json,
    merge_stream_settings,
    wait_for_service_health,
    ensure_process_session,
    append_stream_log,
    start_stream_log_pump,
    persist_settings,
    start_stream_event_lane,
    stop_stream_event_lane,
) -> None:
    @app.post("/control/stream/settings")
    async def stream_settings(request: Request) -> dict[str, object]:
        payload = await read_json(request)
        stream_settings = merge_stream_settings(state.stream_settings, payload)
        stream_settings, notes = _resolve_stream_defaults(stream_settings)
        state.stream_settings = stream_settings
        persist_settings(cfg, state)
        desktop_rows = _device_rows_for_backend(stream_settings.desktop_backend)
        output_selector = _selector_for_output_target(desktop_rows, stream_settings.desktop_output_target)
        capture_selector = _capture_selector_from_settings(stream_settings)
        body = {
            "ok": True,
            "stream_mic_enabled": bool(stream_settings.mic_enabled),
            "stream_desktop_enabled": bool(stream_settings.desktop_enabled),
            "stream_input_mode": stream_settings.input_mode,
            "stream_desktop_output_target": stream_settings.desktop_output_target or "",
            "stream_desktop_capture_input": stream_settings.desktop_capture_input or stream_settings.desktop_device or "",
            "stream_desktop_output_resolved": bool(output_selector),
            "stream_desktop_capture_resolved": bool(capture_selector),
            "stream_desktop_fallback_enabled": bool(_desktop_capture_fallback_enabled()),
            "stream_desktop_output_error": "",
        }
        body.update(native_helper_capabilities())
        if notes.get("desktop_disabled_reason"):
            body["stream_desktop_disabled_reason"] = notes.get("desktop_disabled_reason")
        return body

    @app.post("/control/stream/start")
    async def stream_start(request: Request) -> dict[str, object]:
        payload = await read_json(request)
        stream_settings = merge_stream_settings(state.stream_settings, payload)
        stream_settings, notes = _resolve_stream_defaults(stream_settings)
        selected_desktop_backend = str(desktop_source_backend() or "legacy_ffmpeg")
        use_legacy_desktop_capture = selected_desktop_backend != "native_helper"
        append_stream_log(state, "desktop capture authority: stream-start-v3")
        desktop_output_error = ""
        native_helper_result: dict[str, object] = {}
        native_helper_polled_status: dict[str, object] = {}
        if stream_settings.desktop_enabled:
            output_target = str(stream_settings.desktop_output_target or "").strip()
            if not output_target:
                desktop_output_error = "no_desktop_output_target"
            else:
                state_dir = Path(desktop_audio_receipt_path(cfg)).parent
                try:
                    route = audio_routing_manager.probe_routing(state_dir=state_dir)
                except Exception as exc:
                    route = {}
                    append_stream_log(state, f"desktop output route probe error: {exc}")
                route_ok = _output_route_matches_target(route, output_target)
                append_stream_log(
                    state,
                    "desktop output route probe:"
                    f" target={output_target}"
                    f" current={str(route.get('current_output') or '')}"
                    f" preferred={str(route.get('target_output') or '')}"
                    f" ok={'true' if route_ok else 'false'}",
                )
                if not route_ok:
                    try:
                        ensure_result = audio_routing_manager.ensure_routing(
                            repo_root, state_dir=state_dir
                        )
                    except Exception as exc:
                        ensure_result = {"ok": False, "error": str(exc)}
                    ensure_ok = bool(
                        ensure_result.get("ok", False)
                        if isinstance(ensure_result, dict)
                        else False
                    )
                    route_after = ensure_result.get("routing") if isinstance(ensure_result, dict) else {}
                    if not isinstance(route_after, dict):
                        route_after = {}
                    if not route_after:
                        try:
                            route_after = audio_routing_manager.probe_routing(state_dir=state_dir)
                        except Exception:
                            route_after = {}
                    route_ok = _output_route_matches_target(route_after, output_target)
                    append_stream_log(
                        state,
                        "desktop output route ensure:"
                        f" ok={'true' if ensure_ok else 'false'}"
                        f" target={output_target}"
                        f" current={str(route_after.get('current_output') or '')}"
                        f" preferred={str(route_after.get('target_output') or '')}"
                        f" matched={'true' if route_ok else 'false'}",
                    )
                    if not route_ok:
                        desktop_output_error = "no_desktop_output_route"
        if desktop_output_error:
            notes["desktop_disabled_reason"] = desktop_output_error
            stream_settings = StreamSettings(
                input_mode=stream_settings.input_mode,
                file_path=stream_settings.file_path,
                realtime=bool(stream_settings.realtime),
                mic_enabled=bool(stream_settings.mic_enabled),
                mic_backend=stream_settings.mic_backend,
                mic_device=stream_settings.mic_device,
                desktop_enabled=False,
                desktop_backend=stream_settings.desktop_backend,
                desktop_device=None,
                desktop_output_target=stream_settings.desktop_output_target,
                desktop_capture_input=None,
                event_prefix=stream_settings.event_prefix,
            )
            append_stream_log(
                state,
                f"desktop output route unresolved; desktop capture disabled reason={desktop_output_error}",
            )
        if not process_running_fn(state.process):
            settings = state.settings
            if not settings.profile:
                settings.profile = "cpu_friendly"
            session_id = ensure_process_session(cfg, state)
            state.process = start_service_fn(cfg, settings, session_id=session_id)
            append_stream_log(state, f"service runtime flags: no_vad={'on' if settings.no_vad else 'off'}")
        wait_for_service_health(cfg.service_host, cfg.service_port, timeout_s=6.0)
        if stream_settings.desktop_enabled and selected_desktop_backend == "native_helper":
            state_dir = Path(desktop_audio_receipt_path(cfg)).parent
            # Controller/API calls should default to real desktop capture.
            # Avoid inheriting process-level debug env (e.g. tone mode) unless
            # the caller explicitly asks for a mode in the request payload.
            native_capture_mode = str(
                payload.get("native_capture_mode") or "native-capture"
            ).strip() or "native-capture"
            native_rows = _device_rows_for_backend(stream_settings.desktop_backend)
            native_output_sel = _selector_for_output_target(
                native_rows, stream_settings.desktop_output_target
            )
            native_candidates = _capture_candidates(
                native_rows,
                output_target=stream_settings.desktop_output_target,
                input_mode=stream_settings.input_mode,
            )
            configured_native_sel = _parse_device_selector(
                stream_settings.desktop_capture_input
                or stream_settings.desktop_device
                or ""
            )
            native_default_sel = _preferred_native_helper_capture_selector(
                native_rows,
                output_target=stream_settings.desktop_output_target,
                current_selector=(
                    stream_settings.desktop_capture_input
                    or stream_settings.desktop_device
                    or ""
                ),
            )
            # Native helper capture selector authority:
            # 1) explicitly resolved stream capture selector
            # 2) policy-derived selector
            # Never silently override user/stream selector to a different
            # non-output candidate during start.
            if configured_native_sel:
                native_default_sel = configured_native_sel
            explicit_payload_sel = _parse_device_selector(payload.get("native_desktop_device"))
            output_label_low = str(stream_settings.desktop_output_target or "").strip().lower()
            if (not explicit_payload_sel) and ("what-desktop" in output_label_low):
                loopback_preferred = ""
                for sel in native_candidates:
                    if not sel:
                        continue
                    if native_output_sel and sel == native_output_sel:
                        continue
                    lbl = str(_selector_label(native_rows, sel) or "").strip().lower()
                    if ("blackhole" in lbl) or ("loopback" in lbl) or ("soundflower" in lbl):
                        loopback_preferred = sel
                        break
                if loopback_preferred:
                    native_default_sel = loopback_preferred
            native_desktop_device = str(
                explicit_payload_sel
                or native_default_sel
                or stream_settings.desktop_capture_input
                or stream_settings.desktop_device
                or ""
            ).strip()
            def _native_helper_wait_signal(deadline_s: float = 3.0) -> tuple[bool, dict[str, object]]:
                last_hp_local: dict[str, object] = {}
                signal_deadline_local = time.time() + max(0.5, float(deadline_s))
                while time.time() < signal_deadline_local:
                    poll_status = native_desktop_helper_manager.get_status(state_dir=state_dir)
                    hp_poll = (
                        poll_status.get("health_payload")
                        if isinstance(poll_status, dict)
                        and isinstance(poll_status.get("health_payload"), dict)
                        else {}
                    )
                    if hp_poll:
                        last_hp_local = hp_poll
                    poll_chunks = int(last_hp_local.get("chunks_sent") or 0)
                    poll_signal_frames = int(last_hp_local.get("signal_frames") or 0)
                    poll_state = str(last_hp_local.get("capture_state") or "").strip().lower()
                    if (poll_signal_frames > 0) or (poll_chunks > 0 and poll_state in {"signal", "active"}):
                        return True, last_hp_local
                    time.sleep(0.25)
                return False, last_hp_local

            state._native_helper_capture_selector = native_desktop_device
            append_stream_log(
                state,
                "desktop native helper selector:"
                f" selected={native_desktop_device or '<none>'}"
                f" configured={configured_native_sel or '<none>'}"
                f" output_selector={native_output_sel or '<none>'}"
                f" candidates={','.join(native_candidates) if native_candidates else '<none>'}",
            )
            native_helper_result = native_desktop_helper_manager.start(
                state_dir=state_dir,
                session_id=state.current_session_id or "",
                service_host=cfg.service_host,
                service_port=cfg.service_port,
                ws_path="/ingest",
                pair_path="/pair",
                capture_mode=native_capture_mode,
                desktop_device=native_desktop_device,
                health_port=int(payload.get("native_helper_health_port") or 8793),
            )
            if native_helper_result.get("ok"):
                append_stream_log(
                    state,
                    "desktop native helper start: ok"
                    f" mode={native_capture_mode} device={native_desktop_device or '<none>'}",
                )
                ping_result = _emit_desktop_start_ping()
                if ping_result.get("ok"):
                    append_stream_log(
                        state,
                        "desktop native helper ping:"
                        f" ok=true"
                        f" sound={str(ping_result.get('sound') or '')}"
                        f" pid={int(ping_result.get('pid') or 0)}",
                    )
                else:
                    append_stream_log(
                        state,
                        "desktop native helper ping:"
                        f" ok=false"
                        f" reason={str(ping_result.get('error') or 'unknown')}"
                        f" detail={str(ping_result.get('detail') or '')}",
                    )
                # Startup signal gate: helper must emit signal-bearing chunks
                # shortly after desktop setup/start, otherwise hard-fail.
                signal_ok, last_hp = _native_helper_wait_signal(deadline_s=3.0)
                if (not signal_ok) and native_candidates:
                    retry_candidates = [
                        sel for sel in native_candidates
                        if sel and sel != native_desktop_device
                    ]
                    retry_sel = retry_candidates[0] if retry_candidates else ""
                    if retry_sel:
                        append_stream_log(
                            state,
                            "desktop native helper startup retry:"
                            f" from={native_desktop_device or '<none>'}"
                            f" to={retry_sel}",
                        )
                        _ = native_desktop_helper_manager.stop(state_dir=state_dir)
                        native_desktop_device = retry_sel
                        state._native_helper_capture_selector = native_desktop_device
                        stream_settings = _with_desktop_capture_input(stream_settings, native_desktop_device)
                        state.stream_settings = stream_settings
                        native_helper_result = native_desktop_helper_manager.start(
                            state_dir=state_dir,
                            session_id=state.current_session_id or "",
                            service_host=cfg.service_host,
                            service_port=cfg.service_port,
                            ws_path="/ingest",
                            pair_path="/pair",
                            capture_mode=native_capture_mode,
                            desktop_device=native_desktop_device,
                            health_port=int(payload.get("native_helper_health_port") or 8793),
                        )
                        if native_helper_result.get("ok"):
                            append_stream_log(
                                state,
                                "desktop native helper retry start: ok"
                                f" mode={native_capture_mode} device={native_desktop_device or '<none>'}",
                            )
                            signal_ok, last_hp = _native_helper_wait_signal(deadline_s=3.0)
                        else:
                            signal_ok = False
                            last_hp = {}
                try:
                    native_helper_polled_status = native_desktop_helper_manager.get_status(state_dir=state_dir)
                except Exception:
                    native_helper_polled_status = {}
                if isinstance(native_helper_polled_status, dict) and native_helper_polled_status:
                    if not isinstance(native_helper_result, dict):
                        native_helper_result = {"ok": bool(signal_ok)}
                    native_helper_result["status"] = native_helper_polled_status
                if not signal_ok:
                    poll_chunks = int(last_hp.get("chunks_sent") or 0)
                    poll_state = str(last_hp.get("capture_state") or "").strip().lower()
                    poll_err = str(last_hp.get("last_error") or "").strip()
                    append_stream_log(
                        state,
                        "desktop native helper startup failed:"
                        f" no_signal_in_3s chunks={poll_chunks}"
                        f" capture_state={poll_state or '<none>'}"
                        f" last_error={poll_err or '<none>'}"
                        f" device={native_desktop_device or '<none>'}",
                    )
                    _ = native_desktop_helper_manager.stop(state_dir=state_dir)
                    native_helper_result = {
                        "ok": False,
                        "error": "no_signal_3s",
                        "status": native_desktop_helper_manager.get_status(state_dir=state_dir),
                    }
                    desktop_output_error = "native_helper_no_signal_3s"
                    notes["desktop_disabled_reason"] = desktop_output_error
                    stream_settings = StreamSettings(
                        input_mode=stream_settings.input_mode,
                        file_path=stream_settings.file_path,
                        realtime=bool(stream_settings.realtime),
                        mic_enabled=bool(stream_settings.mic_enabled),
                        mic_backend=stream_settings.mic_backend,
                        mic_device=stream_settings.mic_device,
                        desktop_enabled=False,
                        desktop_backend=stream_settings.desktop_backend,
                        desktop_device=None,
                        desktop_output_target=stream_settings.desktop_output_target,
                        desktop_capture_input=None,
                        event_prefix=stream_settings.event_prefix,
                    )
            else:
                native_err = str(native_helper_result.get("error") or "native_helper_start_failed")
                append_stream_log(
                    state,
                    f"desktop native helper start: failed ({native_err})",
                )
                desktop_output_error = native_err
                notes["desktop_disabled_reason"] = f"native_helper_{native_err}"
                stream_settings = StreamSettings(
                    input_mode=stream_settings.input_mode,
                    file_path=stream_settings.file_path,
                    realtime=bool(stream_settings.realtime),
                    mic_enabled=bool(stream_settings.mic_enabled),
                    mic_backend=stream_settings.mic_backend,
                    mic_device=stream_settings.mic_device,
                    desktop_enabled=False,
                    desktop_backend=stream_settings.desktop_backend,
                    desktop_device=None,
                    desktop_output_target=stream_settings.desktop_output_target,
                    desktop_capture_input=None,
                    event_prefix=stream_settings.event_prefix,
                )
        if process_running_fn(state.client_process):
            stop_client_fn(state.client_process)
        desktop_rows: list[str] = []
        desktop_candidates: list[str] = []
        fallback_enabled = _desktop_capture_fallback_enabled()
        if stream_settings.desktop_enabled:
            desktop_rows = _device_rows_for_backend(stream_settings.desktop_backend)
            desktop_candidates = _capture_candidates(
                desktop_rows,
                output_target=stream_settings.desktop_output_target,
                input_mode=stream_settings.input_mode,
            )
            if desktop_candidates:
                candidate_labels = [
                    f"{sel}={_selector_label(desktop_rows, sel) or '<unknown>'}"
                    for sel in desktop_candidates
                ]
                append_stream_log(
                    state,
                    "desktop candidates: " + " | ".join(candidate_labels),
                )
            current_sel = _capture_selector_from_settings(stream_settings)
            if desktop_candidates and current_sel not in set(desktop_candidates):
                preferred = desktop_candidates[0]
                append_stream_log(
                    state,
                    f"desktop device rebind: {current_sel or '<none>'} -> {preferred}",
                )
                stream_settings = _with_desktop_capture_input(stream_settings, preferred)
                current_sel = preferred
                state.stream_settings = stream_settings
            if current_sel:
                append_stream_log(state, f"desktop device: {current_sel}")
            append_stream_log(
                state,
                "desktop capture binding:"
                f" output_target={stream_settings.desktop_output_target or ''}"
                f" output_selector={_selector_for_output_target(desktop_rows, stream_settings.desktop_output_target) or ''}"
                f" capture_input={current_sel or ''}"
                f" capture_label={_selector_label(desktop_rows, current_sel) if current_sel else ''}",
            )
            if desktop_rows:
                append_stream_log(state, "available desktop devices:")
                for row in desktop_rows:
                    parsed = _parse_device_selector(row)
                    mark = "*" if parsed and parsed == current_sel else "-"
                    append_stream_log(state, f"  {mark} {row}")
        state.stream_settings = stream_settings
        start_stream_event_lane(cfg, state)
        start_seq = state.stream_log_seq
        state.client_process = start_client_fn(cfg, stream_settings)
        append_stream_log(
            state,
            "stream settings:"
            f" mode={stream_settings.input_mode}"
            f" mic_enabled={'true' if stream_settings.mic_enabled else 'false'}"
            f" mic_backend={stream_settings.mic_backend or ''}"
            f" mic_device={stream_settings.mic_device or ''}"
            f" desktop_enabled={'true' if stream_settings.desktop_enabled else 'false'}"
            f" desktop_backend={stream_settings.desktop_backend or ''}"
            f" desktop_capture_input={stream_settings.desktop_capture_input or ''}",
        )
        append_stream_log(
            state,
            f"starting: what client --local --input {stream_settings.input_mode} --host {cfg.service_host} --port {cfg.service_port}",
        )
        append_stream_log(
            state,
            f"client runtime flags: captions_on=forced event_prefix={stream_settings.event_prefix or ''}",
        )
        start_stream_log_pump(state, state.client_process)
        desktop_probe_state = ""
        desktop_fallback_to = ""
        native_health_payload: dict[str, object] = {}
        if (stream_settings.desktop_enabled and use_legacy_desktop_capture and len(desktop_candidates) == 1):
            current_sel = _capture_selector_from_settings(stream_settings)
            probe = _wait_for_desktop_probe_state(state, after_seq=start_seq, timeout_s=8.0)
            desktop_probe_state = probe or desktop_probe_state
            append_stream_log(
                state,
                f"desktop capture startup probe: state={probe or 'none'} candidate={current_sel or '<none>'}",
            )
            output_low = str(stream_settings.desktop_output_target or "").strip().lower()
            snapshot = DesktopProbeSnapshot(
                probe_state=probe or "",
                selector_label=output_low,
            )
            detail_code, detail_bytes = _latest_desktop_probe_detail(state, after_seq=start_seq)
            true_zero_single = _should_rebuild_for_true_zero(
                probe_state=probe or "",
                detail_code=detail_code,
                detail_bytes=detail_bytes,
                scans=[(current_sel or "", str(probe or ""), 0)],
            )
            should_retry = should_retry_single_candidate(snapshot) or true_zero_single
            if should_retry and "what-desktop" in output_low:
                try:
                    state_dir = Path(desktop_audio_receipt_path(cfg)).parent
                    ensure_result = audio_routing_manager.ensure_routing(repo_root, state_dir=state_dir)
                    append_stream_log(
                        state,
                        "desktop routing ensure during start:"
                        f" ok={'true' if bool(ensure_result.get('ok')) else 'false'}"
                        f" changed={'true' if bool(ensure_result.get('changed')) else 'false'}",
                    )
                except Exception as exc:
                    append_stream_log(state, f"desktop routing ensure during start: error ({exc})")
                if true_zero_single:
                    append_stream_log(
                        state,
                        "desktop capture startup true-zero detected; forcing single-candidate retry",
                    )
                stop_client_fn(state.client_process)
                state.client_process = start_client_fn(cfg, stream_settings)
                append_stream_log(
                    state,
                    "desktop capture startup retry:"
                    f" desktop_capture_input={stream_settings.desktop_capture_input or ''}",
                )
                start_stream_log_pump(state, state.client_process)
                start_seq = state.stream_log_seq
                probe_retry = _wait_for_desktop_probe_state(state, after_seq=start_seq, timeout_s=8.0)
                if probe_retry:
                    desktop_probe_state = probe_retry
                append_stream_log(
                    state,
                    f"desktop capture startup retry probe: state={probe_retry or 'none'} candidate={current_sel or '<none>'}",
                )
        if (stream_settings.desktop_enabled and use_legacy_desktop_capture and len(desktop_candidates) > 1 and fallback_enabled):
            current_sel = _capture_selector_from_settings(stream_settings)
            max_switches = max(0, min(2, len(desktop_candidates) - 1))
            switches = 0
            silent_scan_deadline = time.time() + 10.0
            rebuilt_for_true_zero = False
            while True:
                probe = _wait_for_desktop_probe_state(state, after_seq=start_seq, timeout_s=8.0)
                desktop_probe_state = probe or desktop_probe_state
                append_stream_log(
                    state,
                    f"desktop capture fallback probe: state={probe or 'none'} candidates={len(desktop_candidates)} current={current_sel or '<none>'}",
                )
                if probe in {"active", "signal"}:
                    break
                current_label = _selector_label(desktop_rows, current_sel).lower()
                detail_code, detail_bytes = _latest_desktop_probe_detail(state, after_seq=start_seq)
                if probe == "silent":
                    scans = _scan_candidate_levels(
                        str(stream_settings.desktop_backend or ""),
                        desktop_candidates,
                    )
                    append_stream_log(
                        state,
                        "desktop capture scan: "
                        + " | ".join(
                            f"{sel}:{st}:{lvl}" for sel, st, lvl in scans
                        ),
                    )
                    if (
                        not rebuilt_for_true_zero
                        and _should_rebuild_for_true_zero(
                            probe_state=probe or "",
                            detail_code=detail_code,
                            detail_bytes=detail_bytes,
                            scans=scans,
                        )
                    ):
                        rebuilt_for_true_zero = True
                        append_stream_log(
                            state,
                            "desktop capture true-zero startup detected; rebuilding managed routing once",
                        )
                        try:
                            state_dir = Path(desktop_audio_receipt_path(cfg)).parent
                            remove_result = audio_routing_manager.remove_managed_routing(
                                repo_root, state_dir=state_dir
                            )
                            ensure_result = audio_routing_manager.ensure_routing(
                                repo_root, state_dir=state_dir
                            )
                            append_stream_log(
                                state,
                                "desktop capture routing rebuild:"
                                f" remove_ok={'true' if bool(remove_result.get('ok')) else 'false'}"
                                f" ensure_ok={'true' if bool(ensure_result.get('ok')) else 'false'}",
                            )
                        except Exception as exc:
                            append_stream_log(state, f"desktop capture routing rebuild error: {exc}")
                        stop_client_fn(state.client_process)
                        state.client_process = start_client_fn(cfg, stream_settings)
                        append_stream_log(
                            state,
                            "desktop capture startup retry after routing rebuild:"
                            f" desktop_capture_input={stream_settings.desktop_capture_input or ''}",
                        )
                        start_stream_log_pump(state, state.client_process)
                        start_seq = state.stream_log_seq
                        continue
                    signal_hits = [sel for sel, st, lvl in scans if st == "signal" and lvl > 0]
                    if signal_hits:
                        promoted = signal_hits[0]
                    else:
                        promoted = _pick_signal_candidate(
                            str(stream_settings.desktop_backend or ""),
                            desktop_candidates,
                            current_sel,
                        )
                    if (
                        (not promoted or promoted == current_sel)
                        and time.time() < silent_scan_deadline
                    ):
                        time.sleep(1.0)
                        continue
                    if promoted and promoted != current_sel:
                        append_stream_log(
                            state,
                            f"desktop capture candidate promote: {current_sel or '<none>'} -> {promoted}",
                        )
                        stop_client_fn(state.client_process)
                        stream_settings = _with_desktop_capture_input(stream_settings, promoted)
                        state.stream_settings = stream_settings
                        state.client_process = start_client_fn(cfg, stream_settings)
                        start_stream_log_pump(state, state.client_process)
                        current_sel = promoted
                        start_seq = state.stream_log_seq
                        switches += 1
                        continue
                snapshot = DesktopProbeSnapshot(
                    probe_state=probe or "",
                    code=detail_code,
                    byte_count=detail_bytes,
                    selector_label=current_label,
                )
                decision = classify_probe(snapshot)
                if decision.action != "fallback":
                    append_stream_log(
                        state,
                        "desktop capture fallback: keep current"
                        f" reason={decision.reason}"
                        f" code={'' if detail_code is None else detail_code}"
                        f" bytes={'' if detail_bytes is None else detail_bytes}",
                    )
                    break
                if not should_switch_candidate(snapshot, switches=switches, max_switches=max_switches):
                    append_stream_log(state, "desktop capture fallback: exhausted candidates")
                    break
                try:
                    idx = desktop_candidates.index(current_sel)
                except ValueError:
                    idx = -1
                fallback_sel = ""
                ordered = desktop_candidates
                if idx >= 0:
                    ordered = desktop_candidates[idx + 1 :] + desktop_candidates[:idx]
                for cand in ordered:
                    if cand != current_sel:
                        fallback_sel = cand
                        break
                if not fallback_sel:
                    append_stream_log(state, "desktop capture fallback: no alternate candidate available")
                    break
                desktop_fallback_to = fallback_sel
                append_stream_log(
                    state,
                    f"desktop capture fallback: switching {current_sel or '<none>'} -> {fallback_sel} after silent probe",
                )
                stop_client_fn(state.client_process)
                stream_settings = _with_desktop_capture_input(stream_settings, fallback_sel)
                state.stream_settings = stream_settings
                state.client_process = start_client_fn(cfg, stream_settings)
                append_stream_log(
                    state,
                    "stream settings:"
                    f" mode={stream_settings.input_mode}"
                    f" mic_enabled={'true' if stream_settings.mic_enabled else 'false'}"
                    f" mic_backend={stream_settings.mic_backend or ''}"
                    f" mic_device={stream_settings.mic_device or ''}"
                    f" desktop_enabled={'true' if stream_settings.desktop_enabled else 'false'}"
                    f" desktop_backend={stream_settings.desktop_backend or ''}"
                    f" desktop_capture_input={stream_settings.desktop_capture_input or ''}",
                )
                start_stream_log_pump(state, state.client_process)
                current_sel = fallback_sel
                start_seq = state.stream_log_seq
                switches += 1
        elif (stream_settings.desktop_enabled and use_legacy_desktop_capture and len(desktop_candidates) > 1 and not fallback_enabled):
            # Even with continuous fallback disabled, do a one-time startup scan
            # to avoid getting stuck on a silent selector after device index drift.
            current_sel = _capture_selector_from_settings(stream_settings)
            probe = _wait_for_desktop_probe_state(state, after_seq=start_seq, timeout_s=8.0)
            if probe:
                desktop_probe_state = probe
            append_stream_log(
                state,
                f"desktop startup single-pass probe: state={probe or 'none'} current={current_sel or '<none>'}",
            )
            if probe == "silent":
                # Validate output route again at startup-silent time; some apps
                # can steal default output shortly after stream start.
                route_now: dict = {}
                route_ok_now = False
                try:
                    state_dir = Path(desktop_audio_receipt_path(cfg)).parent
                    route_now = audio_routing_manager.probe_routing(state_dir=state_dir)
                    route_ok_now = _output_route_matches_target(
                        route_now, str(stream_settings.desktop_output_target or "")
                    )
                except Exception as exc:
                    append_stream_log(state, f"desktop startup route recheck error: {exc}")
                append_stream_log(
                    state,
                    "desktop startup route recheck:"
                    f" target={stream_settings.desktop_output_target or ''}"
                    f" current={str(route_now.get('current_output') or '')}"
                    f" preferred={str(route_now.get('target_output') or '')}"
                    f" ok={'true' if route_ok_now else 'false'}",
                )
                if not route_ok_now and str(stream_settings.desktop_output_target or "").strip():
                    try:
                        ensure_route = audio_routing_manager.ensure_routing(
                            repo_root, state_dir=state_dir
                        )
                        append_stream_log(
                            state,
                            "desktop startup route re-ensure:"
                            f" ok={'true' if bool(ensure_route.get('ok')) else 'false'}"
                            f" changed={'true' if bool(ensure_route.get('changed')) else 'false'}",
                        )
                        stop_client_fn(state.client_process)
                        state.client_process = start_client_fn(cfg, stream_settings)
                        append_stream_log(
                            state,
                            "desktop startup route re-ensure restart:"
                            f" desktop_capture_input={stream_settings.desktop_capture_input or ''}",
                        )
                        start_stream_log_pump(state, state.client_process)
                        start_seq = state.stream_log_seq
                        probe_after_reroute = _wait_for_desktop_probe_state(
                            state, after_seq=start_seq, timeout_s=8.0
                        )
                        if probe_after_reroute:
                            desktop_probe_state = probe_after_reroute
                        append_stream_log(
                            state,
                            f"desktop startup route re-ensure probe: state={probe_after_reroute or 'none'}",
                        )
                    except Exception as exc:
                        append_stream_log(state, f"desktop startup route re-ensure error: {exc}")
                detail_code, detail_bytes = _latest_desktop_probe_detail(state, after_seq=start_seq)
                scans = _scan_candidate_levels(
                    str(stream_settings.desktop_backend or ""),
                    desktop_candidates,
                )
                append_stream_log(
                    state,
                    "desktop startup single-pass scan: "
                    + " | ".join(f"{sel}:{st}:{lvl}" for sel, st, lvl in scans),
                )
                promoted = ""
                for sel, st, lvl in scans:
                    if st == "signal" and int(lvl) > 0:
                        promoted = sel
                        break
                if promoted and promoted != current_sel:
                    append_stream_log(
                        state,
                        f"desktop startup single-pass promote: {current_sel or '<none>'} -> {promoted}",
                    )
                    stop_client_fn(state.client_process)
                    stream_settings = _with_desktop_capture_input(stream_settings, promoted)
                    state.stream_settings = stream_settings
                    state.client_process = start_client_fn(cfg, stream_settings)
                    append_stream_log(
                        state,
                        "stream settings:"
                        f" mode={stream_settings.input_mode}"
                        f" mic_enabled={'true' if stream_settings.mic_enabled else 'false'}"
                        f" mic_backend={stream_settings.mic_backend or ''}"
                        f" mic_device={stream_settings.mic_device or ''}"
                        f" desktop_enabled={'true' if stream_settings.desktop_enabled else 'false'}"
                        f" desktop_backend={stream_settings.desktop_backend or ''}"
                        f" desktop_capture_input={stream_settings.desktop_capture_input or ''}",
                    )
                    start_stream_log_pump(state, state.client_process)
                    start_seq = state.stream_log_seq
                    probe_after = _wait_for_desktop_probe_state(state, after_seq=start_seq, timeout_s=8.0)
                    if probe_after:
                        desktop_probe_state = probe_after
                    append_stream_log(
                        state,
                        f"desktop startup single-pass promote probe: state={probe_after or 'none'} current={stream_settings.desktop_capture_input or ''}",
                    )
                should_rebuild_single_pass = _should_rebuild_for_true_zero(
                    probe_state=probe or "",
                    detail_code=detail_code,
                    detail_bytes=detail_bytes,
                    scans=scans,
                )
                # Startup logs can arrive slightly out of order; if probe-detail
                # bytes are not yet visible but every candidate scan is true-zero,
                # still force one managed-routing rebuild.
                if (not should_rebuild_single_pass) and detail_bytes is None and _all_silent_zero_scans(scans):
                    append_stream_log(
                        state,
                        "desktop startup single-pass true-zero inferred from candidate scans (detail_bytes pending)",
                    )
                    should_rebuild_single_pass = True
                elif detail_bytes is None and probe == "silent":
                    # Give probe detail a brief chance to land before deciding.
                    time.sleep(0.15)
                    detail_code_retry, detail_bytes_retry = _latest_desktop_probe_detail(
                        state, after_seq=start_seq
                    )
                    if _should_rebuild_for_true_zero(
                        probe_state=probe or "",
                        detail_code=detail_code_retry,
                        detail_bytes=detail_bytes_retry,
                        scans=scans,
                    ):
                        should_rebuild_single_pass = True
                if should_rebuild_single_pass:
                    append_stream_log(
                        state,
                        "desktop startup single-pass true-zero detected; rebuilding managed routing once",
                    )
                    try:
                        state_dir = Path(desktop_audio_receipt_path(cfg)).parent
                        remove_result = audio_routing_manager.remove_managed_routing(
                            repo_root, state_dir=state_dir
                        )
                        ensure_result = audio_routing_manager.ensure_routing(
                            repo_root, state_dir=state_dir
                        )
                        append_stream_log(
                            state,
                            "desktop startup single-pass routing rebuild:"
                            f" remove_ok={'true' if bool(remove_result.get('ok')) else 'false'}"
                            f" ensure_ok={'true' if bool(ensure_result.get('ok')) else 'false'}",
                        )
                    except Exception as exc:
                        append_stream_log(state, f"desktop startup single-pass routing rebuild error: {exc}")
                    stop_client_fn(state.client_process)
                    # Re-resolve rows/candidates post-rebuild, then restart client.
                    desktop_rows = _device_rows_for_backend(stream_settings.desktop_backend)
                    desktop_candidates = _capture_candidates(
                        desktop_rows,
                        output_target=stream_settings.desktop_output_target,
                        input_mode=stream_settings.input_mode,
                    )
                    refreshed_output_target, refreshed_capture_input = resolve_desktop_roles(
                        desktop_rows,
                        current_output_target=stream_settings.desktop_output_target,
                        current_capture_input=stream_settings.desktop_capture_input,
                        legacy_desktop_device=stream_settings.desktop_device,
                    )
                    if refreshed_output_target:
                        stream_settings = StreamSettings(
                            input_mode=stream_settings.input_mode,
                            file_path=stream_settings.file_path,
                            realtime=bool(stream_settings.realtime),
                            mic_enabled=bool(stream_settings.mic_enabled),
                            mic_backend=stream_settings.mic_backend,
                            mic_device=stream_settings.mic_device,
                            desktop_enabled=bool(stream_settings.desktop_enabled),
                            desktop_backend=stream_settings.desktop_backend,
                            desktop_device=stream_settings.desktop_device,
                            desktop_output_target=refreshed_output_target,
                            desktop_capture_input=stream_settings.desktop_capture_input,
                            event_prefix=stream_settings.event_prefix,
                        )
                    stream_settings = _with_desktop_capture_input(
                        stream_settings,
                        refreshed_capture_input or stream_settings.desktop_capture_input or "",
                    )
                    state.stream_settings = stream_settings
                    state.client_process = start_client_fn(cfg, stream_settings)
                    append_stream_log(
                        state,
                        "stream settings:"
                        f" mode={stream_settings.input_mode}"
                        f" mic_enabled={'true' if stream_settings.mic_enabled else 'false'}"
                        f" mic_backend={stream_settings.mic_backend or ''}"
                        f" mic_device={stream_settings.mic_device or ''}"
                        f" desktop_enabled={'true' if stream_settings.desktop_enabled else 'false'}"
                        f" desktop_backend={stream_settings.desktop_backend or ''}"
                        f" desktop_capture_input={stream_settings.desktop_capture_input or ''}",
                    )
                    start_stream_log_pump(state, state.client_process)
                    start_seq = state.stream_log_seq
                    probe_after = _wait_for_desktop_probe_state(state, after_seq=start_seq, timeout_s=8.0)
                    if probe_after:
                        desktop_probe_state = probe_after
                    append_stream_log(
                        state,
                        f"desktop startup single-pass rebuild probe: state={probe_after or 'none'} current={stream_settings.desktop_capture_input or ''}",
                    )
            if not desktop_probe_state:
                append_stream_log(
                    state,
                    "desktop capture fallback disabled: set WHAT_DESKTOP_CAPTURE_FALLBACK_ENABLE=1 to enable continuous candidate switching",
                )
        elif stream_settings.desktop_enabled and (not use_legacy_desktop_capture):
            hp = {}
            if isinstance(native_helper_polled_status, dict) and native_helper_polled_status:
                maybe_hp = native_helper_polled_status.get("health_payload")
                if isinstance(maybe_hp, dict):
                    hp = maybe_hp
            if (not hp) and isinstance(native_helper_result, dict):
                status = native_helper_result.get("status")
                if isinstance(status, dict):
                    maybe_hp = status.get("health_payload")
                    if isinstance(maybe_hp, dict):
                        hp = maybe_hp
            native_health_payload = hp
            helper_capture_state = str(hp.get("capture_state") or "").strip().lower()
            if helper_capture_state in {"signal", "active"}:
                desktop_probe_state = "signal"
            elif helper_capture_state:
                desktop_probe_state = helper_capture_state
            elif bool(native_helper_result.get("ok")):
                desktop_probe_state = "active"
            append_stream_log(
                state,
                "desktop native helper probe:"
                f" state={desktop_probe_state or 'none'}"
                f" capture_backend={str(hp.get('capture_backend') or '').strip().lower()}"
                f" capture_state={helper_capture_state or ''}"
                f" permission_state={str(hp.get('permission_state') or '').strip().lower()}",
            )
        output_selector = _selector_for_output_target(desktop_rows, stream_settings.desktop_output_target)
        capture_selector = _capture_selector_from_settings(stream_settings)
        persist_settings(cfg, state)
        desktop_start_warning = ""
        if (
            stream_settings.desktop_enabled
            and desktop_probe_state in {"silent", "failed", "permission_required", "device_unavailable", "capture_error"}
        ):
            desktop_start_warning = "desktop_capture_silent_with_routed_output"
            append_stream_log(
                state,
                "desktop capture startup warning: routed output is active but capture probe remained silent",
            )
        body = {
            "ok": True,
            "stream_mic_enabled": bool(stream_settings.mic_enabled),
            "stream_desktop_enabled": bool(stream_settings.desktop_enabled),
            "stream_input_mode": stream_settings.input_mode,
            "stream_desktop_device": stream_settings.desktop_capture_input or stream_settings.desktop_device or "",
            "stream_desktop_output_target": stream_settings.desktop_output_target or "",
            "stream_desktop_capture_input": stream_settings.desktop_capture_input or stream_settings.desktop_device or "",
            "stream_desktop_candidate_count": int(len(desktop_candidates)),
            "stream_desktop_output_resolved": bool(output_selector),
            "stream_desktop_capture_resolved": bool(capture_selector),
            "stream_desktop_fallback_enabled": bool(fallback_enabled),
            "stream_desktop_output_error": desktop_output_error,
            "stream_desktop_probe_state": desktop_probe_state,
            "stream_desktop_fallback_to": desktop_fallback_to,
            "stream_desktop_candidates": [
                {
                    "selector": sel,
                    "label": _selector_label(desktop_rows, sel),
                }
                for sel in desktop_candidates
            ],
            "stream_desktop_native_backend": selected_desktop_backend,
            "stream_desktop_native_helper": native_helper_result,
            "stream_desktop_native_capture_backend": str(native_health_payload.get("capture_backend") or ""),
            "stream_desktop_native_capture_selector": str(
                getattr(state, "_native_helper_capture_selector", "") or ""
            ),
        }
        body.update(native_helper_capabilities())
        if desktop_start_warning:
            body["stream_desktop_start_warning"] = desktop_start_warning
        if notes.get("desktop_disabled_reason"):
            body["stream_desktop_disabled_reason"] = notes.get("desktop_disabled_reason")
        return body

    @app.post("/control/stream/stop")
    async def stream_stop(request: Request) -> dict[str, object]:
        payload = await read_json(request)
        preserve_desktop_audio = bool(payload.get("preserve_desktop_audio", False))
        stop_client_fn(state.client_process)
        stop_stream_event_lane(state)
        append_stream_log(state, "client stopped")
        state.client_process = None
        native_backend = str(desktop_source_backend() or "legacy_ffmpeg")
        native_stop_result: dict[str, object] = {}
        if native_backend == "native_helper":
            state_dir = Path(desktop_audio_receipt_path(cfg)).parent
            native_stop_result = native_desktop_helper_manager.stop(state_dir=state_dir)
            if native_stop_result.get("ok"):
                append_stream_log(state, "desktop native helper stop: ok")
            else:
                append_stream_log(
                    state,
                    f"desktop native helper stop: failed ({native_stop_result.get('error') or 'unknown'})",
                )
        # Optional source-state persistence on stop, used by OBS panel toggles.
        if payload:
            stream_settings = merge_stream_settings(state.stream_settings, payload)
            stream_settings, _notes = _resolve_stream_defaults(stream_settings)
            state.stream_settings = stream_settings
            persist_settings(cfg, state)
        uninstall_ok = True
        uninstall_error = ""
        if not preserve_desktop_audio:
            try:
                result = desktop_audio_manager_mod.uninstall(
                    repo_root, Path(desktop_audio_receipt_path(cfg))
                )
                uninstall_ok = bool(result.get("ok", False))
                uninstall_error = str(result.get("error") or "")
                if uninstall_ok:
                    append_stream_log(state, "ui: desktop manager api: auto-uninstall complete")
                else:
                    append_stream_log(
                        state,
                        f"ui: desktop manager api: auto-uninstall partial ({uninstall_error or 'failed'})",
                    )
            except Exception as exc:
                uninstall_ok = False
                uninstall_error = str(exc)
                append_stream_log(state, f"ui: desktop manager api: auto-uninstall error ({uninstall_error})")
        return {
            "ok": True,
            "desktop_audio_uninstall_ok": uninstall_ok,
            "desktop_audio_uninstall_error": uninstall_error,
            "stream_desktop_native_backend": native_backend,
            "stream_desktop_native_helper_stop": native_stop_result,
        }

    @app.get("/control/stream/logs")
    async def stream_logs(offset: int = 0) -> dict[str, object]:
        try:
            stall_after_sec = float(os.environ.get("WHAT_STREAM_EVENT_STALL_SEC", "10.0") or "10.0")
        except Exception:
            stall_after_sec = 10.0
        stall_after_sec = max(2.0, stall_after_sec)
        server_now = time.time()
        with state.stream_log_lock:
            rows = [x for x in state.stream_logs if x[0] > int(offset)]
            next_offset = state.stream_log_seq
            last_event_ts = float(state.stream_log_last_ts or 0.0)
        idle_sec = max(0.0, server_now - last_event_ts) if last_event_ts > 0 else 0.0
        stream_running = bool(process_running_fn(state.client_process))
        # Stall is judged from the heartbeat timestamp only. stream_logs holds
        # non-heartbeat chatter too (e.g. event-lane "starting/connected/stopped"
        # lines appended with count_for_heartbeat=False), so a raw len(rows)==0
        # guard would let that chatter mask a genuine stall while idle_sec — which
        # advances only on heartbeat lines — stays high.
        event_stalled = bool(stream_running and last_event_ts > 0 and idle_sec >= stall_after_sec)
        return {
            "ok": True,
            "lines": [{"seq": seq, "line": line} for seq, line in rows],
            "next_offset": next_offset,
            "server_now_sec": server_now,
            "last_event_sec": last_event_ts,
            "event_idle_sec": idle_sec,
            "event_stall_after_sec": stall_after_sec,
            "stream_running": stream_running,
            "event_stalled": event_stalled,
        }

    @app.get("/control/stream/events")
    async def stream_events(offset: int = 0) -> dict[str, object]:
        try:
            stall_after_sec = float(os.environ.get("WHAT_STREAM_EVENT_STALL_SEC", "10.0") or "10.0")
        except Exception:
            stall_after_sec = 10.0
        stall_after_sec = max(2.0, stall_after_sec)
        server_now = time.time()
        with state.stream_event_lock:
            rows = [x for x in state.stream_events if x[0] > int(offset)]
            next_offset = state.stream_event_seq
            last_event_ts = float(state.stream_event_last_ts or 0.0)
        idle_sec = max(0.0, server_now - last_event_ts) if last_event_ts > 0 else 0.0
        stream_running = bool(process_running_fn(state.client_process))
        event_stalled = bool(
            stream_running and (len(rows) == 0) and last_event_ts > 0 and idle_sec >= stall_after_sec
        )
        return {
            "ok": True,
            "events": [{"seq": seq, "event": event} for seq, event in rows],
            "next_offset": next_offset,
            "server_now_sec": server_now,
            "last_event_sec": last_event_ts,
            "event_idle_sec": idle_sec,
            "event_stall_after_sec": stall_after_sec,
            "stream_running": stream_running,
            "event_stalled": event_stalled,
        }
