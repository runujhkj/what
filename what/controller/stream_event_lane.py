from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from collections import deque
from typing import Any, Callable


def _service_events_url(cfg) -> str:
    host = "127.0.0.1" if str(cfg.service_host or "").strip() in {"", "0.0.0.0"} else str(cfg.service_host)
    path = str(os.environ.get("WHAT_SERVICE_SSE_PATH", "/events") or "/events").strip()
    if not path.startswith("/"):
        path = f"/{path}"
    return f"http://{host}:{int(cfg.service_port)}{path}"


def _env_float(name: str, default: float) -> float:
    raw = str(os.environ.get(name, "")).strip()
    if not raw:
        return float(default)
    try:
        return float(raw)
    except Exception:
        return float(default)


def append_stream_event(state, event: dict[str, Any]) -> None:
    now = time.time()
    with state.stream_event_lock:
        state.stream_event_seq += 1
        state.stream_events.append((state.stream_event_seq, dict(event)))
        state.stream_event_last_ts = now


def reset_stream_event_lane(state) -> None:
    with state.stream_event_lock:
        state.stream_event_seq = 0
        state.stream_events = deque(maxlen=4000)
        state.stream_event_last_ts = 0.0


def start_stream_event_lane(
    *,
    cfg,
    state,
    append_log: Callable[..., None],
    process_running: Callable[[Any], bool],
) -> None:
    thread = getattr(state, "stream_event_thread", None)
    if thread is not None and getattr(thread, "is_alive", lambda: False)():
        return
    stop_evt = threading.Event()
    state.stream_event_stop_event = stop_evt
    reset_stream_event_lane(state)

    def _worker() -> None:
        url = _service_events_url(cfg)
        connect_timeout_sec = max(10.0, _env_float("WHAT_EVENT_LANE_CONNECT_TIMEOUT_SEC", 45.0))
        reconnect_base_sec = max(0.1, _env_float("WHAT_EVENT_LANE_RECONNECT_BASE_SEC", 0.35))
        reconnect_max_sec = max(reconnect_base_sec, _env_float("WHAT_EVENT_LANE_RECONNECT_MAX_SEC", 3.0))
        stall_after_sec = max(2.0, _env_float("WHAT_STREAM_EVENT_STALL_SEC", 10.0))
        append_log(state, f"event lane: starting url={url}", count_for_heartbeat=False)
        last_err_log = 0.0
        reconnect_delay = reconnect_base_sec
        reconnect_attempt = 0
        while not stop_evt.is_set():
            if not process_running(state.process):
                time.sleep(0.15)
                reconnect_delay = reconnect_base_sec
                reconnect_attempt = 0
                continue
            data_lines: list[str] = []
            try:
                req = urllib.request.Request(url, headers={"Accept": "text/event-stream"})
                with urllib.request.urlopen(req, timeout=connect_timeout_sec) as resp:
                    append_log(state, "event lane: connected", count_for_heartbeat=False)
                    reconnect_delay = reconnect_base_sec
                    reconnect_attempt = 0
                    while not stop_evt.is_set():
                        raw = resp.readline()
                        if not raw:
                            raise RuntimeError("event stream closed")
                        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                        if not line or line.startswith(":"):
                            if line == "" and data_lines:
                                body = "\n".join(data_lines).strip()
                                data_lines = []
                                if not body:
                                    continue
                                try:
                                    event = json.loads(body)
                                except Exception:
                                    continue
                                if isinstance(event, dict):
                                    append_stream_event(state, event)
                            continue
                        if line.startswith("data:"):
                            data_lines.append(line[5:].lstrip())
            except Exception as exc:
                if stop_evt.is_set():
                    break
                now = time.time()
                last_event_ts = float(getattr(state, "stream_event_last_ts", 0.0) or 0.0)
                idle_sec = max(0.0, now - last_event_ts) if last_event_ts > 0 else 0.0
                reconnect_attempt += 1
                exc_text = str(exc or "").strip().lower()
                soft_timeout = "timed out" in exc_text
                should_log = (now - last_err_log) >= 2.0 and (
                    (not soft_timeout) or (idle_sec >= stall_after_sec)
                )
                if should_log:
                    append_log(
                        state,
                        "event lane: reconnecting"
                        f" attempt={reconnect_attempt}"
                        f" delay={reconnect_delay:.2f}s"
                        f" idle={idle_sec:.2f}s"
                        f" reason={exc}",
                        count_for_heartbeat=False,
                    )
                    last_err_log = now
                time.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_max_sec, reconnect_delay * 1.8)
        append_log(state, "event lane: stopped", count_for_heartbeat=False)

    state.stream_event_thread = threading.Thread(target=_worker, daemon=True)
    state.stream_event_thread.start()


def stop_stream_event_lane(*, state) -> None:
    stop_evt = getattr(state, "stream_event_stop_event", None)
    if stop_evt is not None:
        try:
            stop_evt.set()
        except Exception:
            pass
    thread = getattr(state, "stream_event_thread", None)
    if thread is not None:
        try:
            thread.join(timeout=1.0)
        except Exception:
            pass
    state.stream_event_stop_event = None
    state.stream_event_thread = None
