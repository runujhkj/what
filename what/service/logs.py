import os
from datetime import datetime


def count_logs_for_date(log_root: str, date_key: str) -> int:
    count = 0
    for root, _, files in os.walk(log_root):
        for name in files:
            if not name.endswith(".jsonl"):
                continue
            path = os.path.join(root, name)
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(path))
            except OSError:
                continue
            if mtime.strftime("%Y%m%d") == date_key:
                count += 1
    return count


def mid_transcript_snippet(transcript: list[str], max_len: int = 40) -> str:
    text = " ".join(t.strip() for t in transcript if t.strip())
    if not text:
        return "no_transcript"
    ascii_text = text.encode("ascii", "ignore").decode("ascii")
    ascii_text = " ".join(ascii_text.split())
    if not ascii_text:
        return "no_transcript"
    if len(ascii_text) > max_len:
        mid = len(ascii_text) // 2
        start = max(0, mid - max_len // 2)
        end = min(len(ascii_text), start + max_len)
        snippet = ascii_text[start:end]
    else:
        snippet = ascii_text
    cleaned = []
    for ch in snippet:
        if ch.isalnum():
            cleaned.append(ch)
        else:
            cleaned.append(" ")
    cleaned_text = " ".join("".join(cleaned).split())
    if not cleaned_text:
        cleaned_text = "no_transcript"
    return cleaned_text.replace(" ", "_")


def finalize_session_log(
    log_path: str,
    session_dir: str,
    log_root: str,
    transcript: list[str],
) -> None:
    if not log_path or not os.path.exists(log_path):
        return
    now = datetime.now()
    date_key = now.strftime("%Y%m%d")
    time_part = now.strftime("%H%M%S")
    count = count_logs_for_date(log_root, date_key)
    snippet = mid_transcript_snippet(transcript)
    filename = f'{date_key}_{count}_T{time_part}_"...{snippet}...".jsonl'
    new_path = os.path.join(session_dir, filename)
    try:
        os.rename(log_path, new_path)
    except OSError:
        pass
