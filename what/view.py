import json
import sys
import urllib.request
from typing import Any
import threading


def _normalize_caption_text(text: str) -> str:
    cleaned = text.translate(str.maketrans("", "", ".?!;:"))
    return " ".join(cleaned.split())


def view_sse(
    url: str,
    client_id: str | None,
    session_id: str | None,
    raw: bool,
    display_mode: str = "delta",
    block_clear: bool = False,
    normalize: bool = True,
    transcript_prefix: str | None = None,
    event_prefix: str | None = None,
    stop_event: threading.Event | None = None,
) -> None:
    raw_events = 0
    matched_events = 0
    dropped_client_mismatch = 0
    warned_no_match = False
    last_text = ""
    sys.stderr.write(
        f"sse: start url={url} client_id={client_id or ''} session_id={session_id or ''} event_prefix={'yes' if event_prefix else 'no'}\n"
    )
    sys.stderr.flush()
    with urllib.request.urlopen(url) as resp:
        for line in resp:
            if stop_event is not None and stop_event.is_set():
                break
            if not line.startswith(b"data:"):
                continue
            payload = line[len(b"data:") :].strip()
            if not payload:
                continue
            event = json.loads(payload.decode("ascii"))
            raw_events += 1
            event_client_id = event.get("client_id")
            # Be tolerant when upstream events omit client_id; only reject
            # when an explicit non-matching client_id is present.
            if client_id and event_client_id and event_client_id != client_id:
                dropped_client_mismatch += 1
                if dropped_client_mismatch <= 5:
                    sys.stderr.write(
                        f"sse: drop client mismatch expected={client_id} got={event_client_id}\n"
                    )
                    sys.stderr.flush()
                continue
            if session_id and event.get("session_id") != session_id:
                continue
            matched_events += 1
            if event_prefix:
                sys.stdout.write(f"{event_prefix}{json.dumps(event, ensure_ascii=True)}\n")
                sys.stdout.flush()
                if matched_events <= 3:
                    sys.stderr.write(
                        f"sse: event pass type={event.get('type', '')} client_id={event_client_id or ''}\n"
                    )
                    sys.stderr.flush()
                continue
            last_text = _print_event(
                event,
                raw,
                display_mode,
                block_clear,
                normalize,
                last_text,
                transcript_prefix,
            )
            if not warned_no_match and raw_events >= 20 and matched_events == 0:
                warned_no_match = True
                sys.stderr.write(
                    f"sse: warning raw_events={raw_events} matched={matched_events} dropped_client_mismatch={dropped_client_mismatch}\n"
                )
                sys.stderr.flush()


def _print_event(
    event: dict[str, Any],
    raw: bool,
    display_mode: str,
    block_clear: bool,
    normalize: bool,
    last_text: str,
    transcript_prefix: str | None,
) -> str:
    if raw:
        sys.stdout.write(json.dumps(event, ensure_ascii=True) + "\n")
        sys.stdout.flush()
        return last_text
    text = event.get("display_text")
    mode = (event.get("display_mode") or display_mode or "delta").lower()
    if text is None:
        text = event.get("text", "")
        if normalize:
            text = _normalize_caption_text(text)
    if transcript_prefix and text:
        sys.stdout.write(f"{transcript_prefix}{text}\n")
        sys.stdout.flush()
        return text or last_text
    clear = event.get("display_clear", block_clear)
    client_id = event.get("client_id", "")
    if text:
        prefix = "" if mode in {"delta", "block"} else (f"[{client_id}] " if client_id else "")
        if mode == "delta":
            delta = _delta_text(last_text, text)
            if delta:
                sys.stdout.write(prefix + delta + " ")
        elif mode == "block":
            if clear and sys.stdout.isatty():
                sys.stdout.write("\033[H\033[J")
            sys.stdout.write(prefix + text + "\n")
        else:
            sys.stdout.write(prefix + text + "\n")
        sys.stdout.flush()
    return text or last_text


def _delta_text(prev: str, current: str) -> str:
    if not prev:
        return current
    max_check = min(len(prev), len(current))
    for k in range(max_check, 0, -1):
        if prev.endswith(current[:k]):
            return current[k:]
    return current
