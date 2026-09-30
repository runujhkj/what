from pathlib import Path
import subprocess
import time
import re
from types import SimpleNamespace

from fastapi import FastAPI, Request

from . import audio_routing_manager
from . import desktop_audio_output_runtime
from . import native_desktop_helper_manager
from .native_desktop_backend import native_helper_capabilities
from .desktop_source_authority import parse_desktop_device_rows, resolve_desktop_roles
from .types import ControllerConfig
from .state import ControllerState
from ..desktop_audio import list_desktop_devices, normalize_desktop_backend, default_desktop_backend
from ..live_audio_probe import measure_live_source
from .routes_desktop_audio_logs import (
    build_install_log_lines,
    build_uninstall_log_lines,
)


def register_desktop_audio_routes(
    app: FastAPI,
    cfg: ControllerConfig,
    state: ControllerState,
    *,
    repo_root,
    desktop_audio_manager_mod,
    read_json,
    ensure_process_session,
    append_stream_log,
    desktop_audio_receipt_path,
) -> None:
    def _score_probe_state(state_name: str, level: int) -> int:
        score = int(level)
        if state_name == "signal":
            score += 10_000
        elif state_name == "silent":
            score += 100
        return score

    def _as_int(value: object, default: int = 0) -> int:
        try:
            if value is None:
                return int(default)
            return int(value)
        except Exception:
            return int(default)

    def _prefer_loopback_capture_selector(rows: list[str], fallback: str) -> str:
        parsed = parse_desktop_device_rows(rows)
        for row in parsed:
            if row.is_mic_like:
                continue
            if row.is_loopback_like:
                return row.selector
        return str(fallback or "").strip()

    def _autoprobe_capture_selector(
        *,
        rows: list[str],
        desktop_backend: str,
        fallback_selector: str,
    ) -> tuple[str, list[tuple[str, str, int, int, int]]]:
        parsed = parse_desktop_device_rows(rows)
        non_mic = [row for row in parsed if (not row.is_mic_like and str(row.selector or "").startswith(":"))]
        preferred = [row for row in non_mic if (row.is_loopback_like or row.is_what_target)]
        candidates = preferred if preferred else non_mic
        candidates = candidates[:6]
        scored: list[tuple[int, int, int, str]] = []
        traces: list[tuple[str, str, int, int, int]] = []
        for row in candidates:
            try:
                sample = measure_live_source(
                    "desktop",
                    SimpleNamespace(
                        desktop_backend=str(desktop_backend or "avfoundation"),
                        desktop_device=str(row.selector),
                        mic_backend="",
                        mic_device="",
                    ),
                    SimpleNamespace(sample_rate=16000, channels=1),
                    duration_sec=0.25,
                )
            except Exception:
                sample = {"state": "error", "level": -1, "rms": -1, "bytes": 0}
            state_name = str(sample.get("state", "error"))
            level = _as_int(sample.get("level"), -1)
            rms = _as_int(sample.get("rms"), -1)
            nbytes = _as_int(sample.get("bytes"), 0)
            traces.append((str(row.selector), state_name, level, rms, nbytes))
            score = _score_probe_state(state_name, level)
            if row.is_loopback_like:
                score += 3_000
            if row.is_what_target:
                score += 1_500
            scored.append((score, rms, nbytes, str(row.selector)))
        if scored:
            scored.sort(reverse=True)
            best = str(scored[0][3] or "")
            if best:
                return best, traces
        return str(fallback_selector or "").strip(), traces

    def _probe_selector_rows(
        *,
        rows: list[str],
        desktop_backend: str,
        duration_sec: float,
    ) -> tuple[list[dict[str, object]], str]:
        parsed = parse_desktop_device_rows(rows)
        selector_to_label = {str(r.selector): str(r.label) for r in parsed}
        out_rows: list[dict[str, object]] = []
        scored: list[tuple[int, int, int, str]] = []
        for row in parsed:
            if row.is_mic_like:
                continue
            selector = str(row.selector or "").strip()
            if not selector.startswith(":"):
                continue
            try:
                sample = measure_live_source(
                    "desktop",
                    SimpleNamespace(
                        desktop_backend=str(desktop_backend or "avfoundation"),
                        desktop_device=selector,
                        mic_backend="",
                        mic_device="",
                    ),
                    SimpleNamespace(sample_rate=16000, channels=1),
                    duration_sec=duration_sec,
                )
            except Exception as exc:
                sample = {"state": "error", "level": -1, "rms": -1, "bytes": 0, "error": str(exc)}
            state_name = str(sample.get("state", "error"))
            level = _as_int(sample.get("level"), -1)
            rms = _as_int(sample.get("rms"), -1)
            nbytes = _as_int(sample.get("bytes"), 0)
            scored.append((_score_probe_state(state_name, level), rms, nbytes, selector))
            out_rows.append(
                {
                    "selector": selector,
                    "label": selector_to_label.get(selector, selector),
                    "state": state_name,
                    "level": level,
                    "rms": rms,
                    "bytes": nbytes,
                    "code": _as_int(sample.get("code"), -1),
                    "stderr": str(sample.get("stderr", "")),
                }
            )
        selected = ""
        if scored:
            scored.sort(reverse=True)
            selected = str(scored[0][3] or "")
        return out_rows, selected

    def _play_test_ping() -> tuple[bool, str]:
        try:
            # Keep this deterministic and short on macOS where this module runs.
            subprocess.run(
                ["afplay", "/System/Library/Sounds/Ping.aiff"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3.0,
            )
            return True, ""
        except Exception as exc:
            return False, str(exc)

    def _normalize_device_rows(raw_devices: list[str]) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for row in raw_devices:
            text = str(row or "").strip()
            if not text:
                continue
            m = re.match(r"^\s*(\d+)\s*:\s*(.+?)\s*$", text)
            if m:
                rows.append({"value": f":{m.group(1)}", "label": m.group(2)})
            else:
                rows.append({"value": text, "label": text})
        return rows

    @app.get("/control/desktop-audio/status")
    async def desktop_audio_status(include_routing: bool = True) -> dict[str, object]:
        return {
            "ok": True,
            "status": desktop_audio_manager_mod.get_status(
                repo_root,
                Path(desktop_audio_receipt_path(cfg)),
                include_routing=bool(include_routing),
            ),
        }

    @app.get("/control/desktop-audio/devices")
    async def desktop_audio_devices(backend: str | None = None) -> dict[str, object]:
        selected_backend = normalize_desktop_backend(backend or default_desktop_backend())
        devices = _normalize_device_rows(list_desktop_devices(selected_backend))
        return {
            "ok": True,
            "backend": selected_backend,
            "devices": devices,
        }

    @app.get("/control/desktop-audio/probe-capture")
    async def desktop_audio_probe_capture(
        backend: str | None = None,
        duration_sec: float = 0.25,
    ) -> dict[str, object]:
        selected_backend = normalize_desktop_backend(backend or default_desktop_backend())
        try:
            raw_rows = list_desktop_devices(selected_backend)
        except Exception:
            raw_rows = []
        rows, selected = _probe_selector_rows(
            rows=raw_rows,
            desktop_backend=selected_backend,
            duration_sec=max(0.05, min(1.5, float(duration_sec))),
        )
        return {
            "ok": True,
            "backend": selected_backend,
            "rows": rows,
            "selected": selected,
        }

    @app.post("/control/desktop-audio/ping")
    async def desktop_audio_ping(request: Request) -> dict[str, object]:
        ensure_process_session(cfg, state)
        payload = await read_json(request)
        selected_backend = normalize_desktop_backend(
            str(payload.get("backend") or default_desktop_backend())
        )
        duration_sec = max(0.05, min(1.5, float(payload.get("duration_sec") or 0.35)))
        ok_ping, ping_error = _play_test_ping()
        # Allow the route to settle before probe.
        time.sleep(0.18)
        try:
            raw_rows = list_desktop_devices(selected_backend)
        except Exception:
            raw_rows = []
        rows, selected = _probe_selector_rows(
            rows=raw_rows,
            desktop_backend=selected_backend,
            duration_sec=duration_sec,
        )
        append_stream_log(
            state,
            f"ui: desktop audio ping {'ok' if ok_ping else 'failed'} backend={selected_backend} selected={selected or '<none>'}",
        )
        return {
            "ok": bool(ok_ping),
            "ping_error": str(ping_error or ""),
            "backend": selected_backend,
            "rows": rows,
            "selected": selected,
        }

    @app.post("/control/desktop-audio/install")
    async def desktop_audio_install(request: Request) -> dict[str, object]:
        ensure_process_session(cfg, state)
        payload = await read_json(request)
        configure_routing = True
        mode = str(payload.get("mode") or "").strip().lower()
        if mode == "driver_only":
            configure_routing = False
        if "configure_routing" in payload:
            configure_routing = bool(payload.get("configure_routing"))
        result = desktop_audio_manager_mod.install(
            repo_root,
            Path(desktop_audio_receipt_path(cfg)),
            configure_routing=configure_routing,
        )
        for line in build_install_log_lines(result, configure_routing=configure_routing):
            append_stream_log(state, line)
        return result

    @app.post("/control/desktop-audio/uninstall")
    async def desktop_audio_uninstall() -> dict[str, object]:
        ensure_process_session(cfg, state)
        result = desktop_audio_manager_mod.uninstall(
            repo_root, Path(desktop_audio_receipt_path(cfg))
        )
        for line in build_uninstall_log_lines(result):
            append_stream_log(state, line)
        return result

    @app.post("/control/desktop-audio/admin/warmup")
    async def desktop_audio_admin_warmup() -> dict[str, object]:
        ensure_process_session(cfg, state)
        result = desktop_audio_manager_mod.warmup_admin()
        if result.get("ok"):
            append_stream_log(state, "ui: desktop manager api: admin warmup ok")
        else:
            append_stream_log(
                state,
                f"ui: desktop manager api: admin warmup failed ({result.get('error') or result.get('code') or 'unknown'})",
            )
        return result

    @app.get("/control/desktop-audio/outputs")
    async def desktop_audio_outputs() -> dict[str, object]:
        state_dir = Path(desktop_audio_receipt_path(cfg)).parent
        rows = desktop_audio_output_runtime.list_output_rows(repo_root)
        receipt = desktop_audio_output_runtime.read_receipt(
            desktop_audio_output_runtime.routing_receipt_path(state_dir)
        )
        selected = str(receipt.get("selected_output") or "")
        return {
            "ok": True,
            "outputs": rows,
            "selected_output": selected,
        }

    @app.post("/control/desktop-audio/output/select")
    async def desktop_audio_output_select(request: Request) -> dict[str, object]:
        ensure_process_session(cfg, state)
        payload = await read_json(request)
        state_dir = Path(desktop_audio_receipt_path(cfg)).parent
        selected = str(payload.get("output_name") or payload.get("name") or "").strip()
        result = desktop_audio_output_runtime.select_output(state_dir=state_dir, output_name=selected)
        if result.get("ok"):
            append_stream_log(state, f"ui: desktop manager api: selected output: {selected}")
        else:
            append_stream_log(state, "ui: desktop manager api: selected output failed (missing_output_name)")
        return result

    @app.post("/control/desktop-audio/rebuild")
    async def desktop_audio_rebuild() -> dict[str, object]:
        ensure_process_session(cfg, state)
        state_dir = Path(desktop_audio_receipt_path(cfg)).parent
        remove_result = audio_routing_manager.remove_managed_routing(repo_root, state_dir=state_dir)
        ensure_result = audio_routing_manager.ensure_routing(repo_root, state_dir=state_dir)
        ok = bool(ensure_result.get("ok"))
        append_stream_log(
            state,
            f"ui: desktop manager api: rebuild {'ok' if ok else 'failed'}"
            f" (remove={remove_result.get('ok', False)} ensure={ensure_result.get('ok', False)})",
        )
        return {
            "ok": ok,
            "remove_result": remove_result,
            "ensure_result": ensure_result,
        }

    @app.post("/control/desktop-audio/ensure")
    async def desktop_audio_ensure() -> dict[str, object]:
        ensure_process_session(cfg, state)
        state_dir = Path(desktop_audio_receipt_path(cfg)).parent
        ensure_result = audio_routing_manager.ensure_routing(repo_root, state_dir=state_dir)
        ok = bool(ensure_result.get("ok"))
        append_stream_log(
            state,
            f"ui: desktop manager api: ensure {'ok' if ok else 'failed'}",
        )
        return {
            "ok": ok,
            "ensure_result": ensure_result,
        }

    @app.get("/control/native-desktop-helper/status")
    async def native_desktop_helper_status() -> dict[str, object]:
        state_dir = Path(desktop_audio_receipt_path(cfg)).parent
        status = native_desktop_helper_manager.get_status(state_dir=state_dir)
        payload = {"ok": True, "status": status}
        payload.update(native_helper_capabilities())
        return payload

    @app.post("/control/native-desktop-helper/start")
    async def native_desktop_helper_start(request: Request) -> dict[str, object]:
        ensure_process_session(cfg, state)
        payload = await read_json(request)
        state_dir = Path(desktop_audio_receipt_path(cfg)).parent
        capture_mode = str(payload.get("capture_mode") or "native-capture").strip() or "native-capture"
        no_stream = bool(payload.get("no_stream", False))
        explicit_desktop_device = str(payload.get("desktop_device") or "").strip()
        desktop_backend = normalize_desktop_backend(
            str(
                payload.get("desktop_backend")
                or state.stream_settings.desktop_backend
                or default_desktop_backend()
            )
        )
        desktop_device = str(
            payload.get("desktop_device")
            or state.stream_settings.desktop_capture_input
            or state.stream_settings.desktop_device
            or ""
        ).strip()
        probe_trace: list[tuple[str, str, int, int, int]] = []
        if not desktop_device:
            try:
                rows = list_desktop_devices(desktop_backend)
            except Exception:
                rows = []
            _target, resolved_capture = resolve_desktop_roles(
                rows,
                current_output_target=(
                    str(payload.get("desktop_output_target") or "").strip()
                    or state.stream_settings.desktop_output_target
                ),
                current_capture_input="",
                legacy_desktop_device="",
            )
            desktop_device = str(resolved_capture or "").strip()
            # For native helper capture, prefer loopback input selectors
            # (e.g. BlackHole) over aggregate/output labels when auto-binding.
            desktop_device = _prefer_loopback_capture_selector(rows, desktop_device)
            if no_stream and desktop_backend == "avfoundation":
                desktop_device, probe_trace = _autoprobe_capture_selector(
                    rows=rows,
                    desktop_backend=desktop_backend,
                    fallback_selector=desktop_device,
                )
        elif no_stream and desktop_backend == "avfoundation" and not explicit_desktop_device:
            try:
                rows = list_desktop_devices(desktop_backend)
            except Exception:
                rows = []
            desktop_device, probe_trace = _autoprobe_capture_selector(
                rows=rows,
                desktop_backend=desktop_backend,
                fallback_selector=desktop_device,
            )
        if no_stream and desktop_backend == "avfoundation" and probe_trace:
            saw_signal = any(state_name == "signal" for _, state_name, _, _, _ in probe_trace)
            if not saw_signal:
                _ok_ping, _ping_error = _play_test_ping()
                if _ping_error:
                    append_stream_log(
                        state,
                        f"ui: native desktop helper autoprobe ping failed ({_ping_error})",
                    )
                time.sleep(0.2)
                try:
                    rows = list_desktop_devices(desktop_backend)
                except Exception:
                    rows = []
                desktop_device, probe_trace2 = _autoprobe_capture_selector(
                    rows=rows,
                    desktop_backend=desktop_backend,
                    fallback_selector=desktop_device,
                )
                probe_trace.extend(probe_trace2)
        health_port = int(payload.get("health_port") or 8793)
        result = native_desktop_helper_manager.start(
            state_dir=state_dir,
            session_id=state.current_session_id or "",
            service_host=cfg.service_host,
            service_port=cfg.service_port,
            ws_path="/ingest",
            pair_path="/pair",
            capture_mode=capture_mode,
            desktop_device=desktop_device,
            health_port=health_port,
            no_stream=no_stream,
        )
        if result.get("ok"):
            append_stream_log(
                state,
                f"ui: native desktop helper start ok mode={capture_mode} backend={desktop_backend} no_stream={'yes' if no_stream else 'no'} device={desktop_device or '<none>'}",
            )
            for sel, pstate, plevel, prms, pbytes in probe_trace[:6]:
                append_stream_log(
                    state,
                    f"ui: native desktop helper autoprobe: sel={sel} state={pstate} level={plevel} rms={prms} bytes={pbytes}",
                )
        else:
            append_stream_log(
                state,
                f"ui: native desktop helper start failed ({result.get('error') or 'unknown'})",
            )
        return result

    @app.post("/control/native-desktop-helper/stop")
    async def native_desktop_helper_stop() -> dict[str, object]:
        ensure_process_session(cfg, state)
        state_dir = Path(desktop_audio_receipt_path(cfg)).parent
        result = native_desktop_helper_manager.stop(state_dir=state_dir)
        if result.get("ok"):
            append_stream_log(state, "ui: native desktop helper stop ok")
        else:
            append_stream_log(
                state,
                f"ui: native desktop helper stop failed ({result.get('error') or 'unknown'})",
            )
        return result
