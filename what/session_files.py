"""Per-session outputs: an all-source chronological transcript and a single-file archive.

A session directory (``<logs>/<session_id>/``) is written by several processes:

- ``<client_id>.jsonl``: segment events from one client connection (``mic-*``, ``desktop-*``).
  Segment ``abs_start``/``abs_end`` are offsets into the companion recording.
- ``<client_id>.wav``: that connection's recording (appended on reconnect).
- ``corrections.jsonl``: edits saved by the GUI (``what.correction.v1``).
- ``process.log``: the controller's log.

This module adds:

- ``transcript.txt``: every source merged in wall-clock order, each block labelled by source.
- ``<session_id>.what``: a zip archive holding a manifest plus all of the above, so a session
  can be reopened (viewed, edited, replayed, continued) on this or another machine.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import textwrap
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

TRANSCRIPT_NAME = "transcript.txt"
CORRECTIONS_NAME = "corrections.jsonl"
PROCESS_LOG_NAME = "process.log"
MANIFEST_NAME = "manifest.json"
ARCHIVE_SUFFIX = ".what"
ARCHIVE_FORMAT = "what.session"
ARCHIVE_VERSION = 1

# Same rule as the GUI's isSafeId (gui/lib/review_audio.js): ids become path components.
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")

# Consecutive segments from one source closer than this are shown as one block.
BLOCK_GAP_SEC = 4.0

SOURCE_LABELS = {"mic": "Mic", "desktop": "Desktop", "mixed": "Mic + desktop"}


class SessionFileError(Exception):
    """A session directory or archive that cannot be read or written as asked."""


def is_safe_name(name: str) -> bool:
    return bool(_SAFE_NAME.match(name or "")) and ".." not in name


@dataclass
class Segment:
    source: str
    client_id: str
    segment_id: str
    start: float  # wall-clock epoch seconds
    end: float
    text: str
    edited: bool = False


def _read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    try:
        handle = path.open("r", encoding="utf-8", errors="replace")
    except OSError:
        return
    with handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except ValueError:
                continue  # a line cut short by a crash; the rest of the log is still usable
            if isinstance(item, dict):
                yield item


def client_logs(session_dir: Path) -> list[Path]:
    """The per-client segment logs in a session directory."""
    return sorted(
        p for p in Path(session_dir).glob("*.jsonl")
        if p.name != CORRECTIONS_NAME and is_safe_name(p.name)
    )


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def recording_anchor(event: dict[str, Any]) -> float | None:
    """Wall-clock time (epoch s) of sample 0 of the event's recording.

    Segment abs times are recording offsets, so anchor + abs_start is when the speech
    happened. Events carry ``stream_started_at``; older logs only have ``wall_time`` (when
    the event was written, just after its chunk ended), so estimate from that.
    """
    anchor = _number(event.get("stream_started_at"))
    if anchor is not None:
        return anchor
    wall = _number(event.get("wall_time"))
    chunk_end = _number(event.get("chunk_end"))
    if wall is not None and chunk_end is not None:
        return wall - chunk_end
    return None


def source_of(event: dict[str, Any], client_id: str) -> str:
    source = str(event.get("input_source_id") or "").strip()
    if not source:
        source = client_id.split("-", 1)[0]
    return source or "unknown"


def _event_segments(event: dict[str, Any]) -> list[dict[str, Any]]:
    # Matches segmentsOf() in gui/lib/transcript_record.js, so segment ids (and with them
    # correction keys) agree between the GUI and these files.
    segments = event.get("segments")
    if isinstance(segments, list) and segments:
        return [s for s in segments if isinstance(s, dict)]
    text = str(event.get("text") or "")
    if not text.strip():
        return []
    index = event.get("chunk_index")
    return [{
        "id": "" if index is None else f"chunk-{index}",
        "abs_start": event.get("chunk_start"),
        "abs_end": event.get("chunk_end"),
        "text": text,
    }]


def latest_corrections(session_dir: Path) -> dict[tuple[str, str], dict[str, Any]]:
    """The newest correction per (client_id, segment_id)."""
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for item in _read_jsonl(Path(session_dir) / CORRECTIONS_NAME):
        if item.get("schema") != "what.correction.v1":
            continue
        client_id = str(item.get("client_id") or "")
        for segment_id in item.get("segment_ids") or []:
            key = (client_id, str(segment_id))
            previous = latest.get(key)
            revision = _number(item.get("revision")) or 0
            if previous is None or revision >= (_number(previous.get("revision")) or 0):
                latest[key] = item
    return latest


def session_segments(session_dir: Path) -> list[Segment]:
    """Every transcribed segment of the session, corrections applied, in wall-clock order."""
    session_dir = Path(session_dir)
    corrections = latest_corrections(session_dir)
    seen: set[tuple[str, str]] = set()
    out: list[Segment] = []
    for log in client_logs(session_dir):
        fallback_client = log.stem
        for event in _read_jsonl(log):
            if event.get("type") != "segment":
                continue
            client_id = str(event.get("client_id") or fallback_client)
            source = source_of(event, client_id)
            anchor = recording_anchor(event)
            for seg in _event_segments(event):
                text = str(seg.get("text") or "").strip()
                if not text:
                    continue
                segment_id = str(seg.get("id") or "")
                if segment_id:
                    if (client_id, segment_id) in seen:
                        continue
                    seen.add((client_id, segment_id))
                abs_start = _number(seg.get("abs_start"))
                abs_end = _number(seg.get("abs_end"))
                if abs_start is None:
                    abs_start = _number(event.get("chunk_start")) or 0.0
                if abs_end is None:
                    abs_end = abs_start
                base = anchor if anchor is not None else 0.0
                edited = False
                correction = corrections.get((client_id, segment_id)) if segment_id else None
                if correction is not None:
                    text = str(correction.get("corrected_text") or "").strip()
                    edited = True
                    if not text:
                        continue  # deleted in review
                out.append(Segment(source, client_id, segment_id, base + abs_start,
                                   base + max(abs_end, abs_start), text, edited))
    out.sort(key=lambda s: (s.start, s.source, s.client_id))
    return out


@dataclass
class Block:
    source: str
    start: float
    end: float
    texts: list[str]
    edited: bool


def group_blocks(segments: list[Segment], gap_sec: float = BLOCK_GAP_SEC) -> list[Block]:
    blocks: list[Block] = []
    for seg in segments:
        last = blocks[-1] if blocks else None
        if last is not None and last.source == seg.source and seg.start - last.end <= gap_sec:
            last.texts.append(seg.text)
            last.end = max(last.end, seg.end)
            last.edited = last.edited or seg.edited
        else:
            blocks.append(Block(seg.source, seg.start, seg.end, [seg.text], seg.edited))
    return blocks


def source_label(source: str) -> str:
    return SOURCE_LABELS.get(source, source.capitalize() or "Unknown")


def render_transcript(session_dir: Path, *, tz: timezone | None = None) -> str:
    """The session as plain text: one block per stretch of speech, labelled by source."""
    session_dir = Path(session_dir)
    segments = session_segments(session_dir)
    blocks = group_blocks(segments)

    def local(ts: float) -> datetime:
        return datetime.fromtimestamp(ts, tz=tz) if tz else datetime.fromtimestamp(ts)

    lines = [f"What transcript: session {session_dir.name}"]
    sources: dict[str, list[str]] = {}
    for log in client_logs(session_dir):
        first = next(_read_jsonl(log), None) or {}
        source = source_of(first, str(first.get("client_id") or log.stem))
        sources.setdefault(source, []).append(log.stem)
    if sources:
        lines.append("Sources: " + "; ".join(
            f"{source_label(s)} ({', '.join(ids)})" for s, ids in sorted(sources.items())))
    if not blocks:
        lines += ["", "No transcribed speech in this session."]
        return "\n".join(lines) + "\n"

    first_day = local(blocks[0].start).date()
    last_day = local(blocks[-1].end).date()
    multi_day = first_day != last_day
    stamp = "%Y-%m-%d %H:%M:%S" if multi_day else "%H:%M:%S"
    span = f"{local(blocks[0].start):%Y-%m-%d %H:%M:%S} to {local(blocks[-1].end):{stamp}}"
    lines.append(f"Recorded: {span} (local time)")
    if any(b.edited for b in blocks):
        lines.append("Blocks marked (edited) include corrections made in review.")

    for block in blocks:
        header = f"[{local(block.start):{stamp}} - {local(block.end):{stamp}}] {source_label(block.source)}"
        if block.edited:
            header += " (edited)"
        body = textwrap.fill(" ".join(block.texts), width=92,
                             initial_indent="    ", subsequent_indent="    ")
        lines += ["", header, body]
    return "\n".join(lines) + "\n"


def _atomic_write_text(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_transcript(session_dir: Path) -> Path:
    session_dir = Path(session_dir)
    path = session_dir / TRANSCRIPT_NAME
    _atomic_write_text(path, render_transcript(session_dir))
    return path


def archive_path(session_dir: Path) -> Path:
    session_dir = Path(session_dir)
    return session_dir / f"{session_dir.name}{ARCHIVE_SUFFIX}"


def _app_version() -> str:
    try:
        from importlib.metadata import version
        return version("what")
    except Exception:
        return ""


def build_manifest(session_dir: Path) -> dict[str, Any]:
    session_dir = Path(session_dir)
    sources = []
    for log in client_logs(session_dir):
        first = next(_read_jsonl(log), None) or {}
        client_id = str(first.get("client_id") or log.stem)
        wav = log.with_suffix(".wav")
        sources.append({
            "client_id": client_id,
            "source": source_of(first, client_id),
            "transcript": log.name,
            "recording": wav.name if wav.exists() else None,
        })
    def optional(name: str) -> str | None:
        return name if (session_dir / name).exists() else None

    return {
        "format": ARCHIVE_FORMAT,
        "version": ARCHIVE_VERSION,
        "session_id": session_dir.name,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "app_version": _app_version(),
        "sources": sources,
        "corrections": optional(CORRECTIONS_NAME),
        "transcript": optional(TRANSCRIPT_NAME),
        "process_log": optional(PROCESS_LOG_NAME),
    }


def pack_session(session_dir: Path, copy_to: Path | None = None) -> Path:
    """Refresh transcript.txt and write ``<session_dir>/<session_id>.what``.

    With ``copy_to``, also place a copy there (a session opened from, or saved to, a file
    outside the logs folder is kept up to date that way).
    """
    session_dir = Path(session_dir)
    if not session_dir.is_dir():
        raise SessionFileError(f"not a session folder: {session_dir}")
    if not is_safe_name(session_dir.name):
        raise SessionFileError(f"unexpected session folder name: {session_dir.name}")
    write_transcript(session_dir)
    manifest = build_manifest(session_dir)
    members = [s["transcript"] for s in manifest["sources"]]
    members += [s["recording"] for s in manifest["sources"] if s["recording"]]
    members += [manifest[k] for k in ("corrections", "transcript", "process_log") if manifest[k]]

    target = archive_path(session_dir)
    fd, tmp = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(session_dir))
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, "w", allowZip64=True) as zf:
            zf.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2) + "\n",
                        compress_type=zipfile.ZIP_DEFLATED)
            for name in members:
                # PCM barely compresses; storing keeps packing a long session fast.
                kind = zipfile.ZIP_STORED if name.endswith(".wav") else zipfile.ZIP_DEFLATED
                zf.write(session_dir / name, arcname=name, compress_type=kind)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    if copy_to is not None:
        copy_to = Path(copy_to)
        if copy_to.resolve() != target.resolve():
            fd, tmp_copy = tempfile.mkstemp(prefix=f".{copy_to.name}.", dir=str(copy_to.parent))
            os.close(fd)
            try:
                shutil.copyfile(target, tmp_copy)
                os.replace(tmp_copy, copy_to)
            except BaseException:
                try:
                    os.unlink(tmp_copy)
                except OSError:
                    pass
                raise
    return target


def read_manifest(archive: Path) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(archive) as zf:
            manifest = json.loads(zf.read(MANIFEST_NAME).decode("utf-8"))
    except (OSError, zipfile.BadZipFile, KeyError, ValueError) as exc:
        raise SessionFileError(f"not a What session file: {archive} ({exc})") from exc
    if not isinstance(manifest, dict) or manifest.get("format") != ARCHIVE_FORMAT:
        raise SessionFileError(f"not a What session file: {archive}")
    if int(manifest.get("version") or 0) > ARCHIVE_VERSION:
        raise SessionFileError(
            f"{archive} was written by a newer version of What (format v{manifest.get('version')})")
    if not is_safe_name(str(manifest.get("session_id") or "")):
        raise SessionFileError(f"invalid session id in {archive}")
    return manifest


def _first_line(data: bytes) -> bytes:
    return data.split(b"\n", 1)[0].strip()


def unpack_session(archive: Path, logs_dir: Path) -> Path:
    """Place an archive's files into ``<logs_dir>/<session_id>/`` and return that folder.

    The logs are append-only, so where the folder already has a file at least as large as
    the archived copy (the same session, possibly with more recorded since), it is kept.
    A folder holding a different session under the same id is refused.
    """
    archive = Path(archive)
    manifest = read_manifest(archive)
    session_id = str(manifest["session_id"])
    target = Path(logs_dir) / session_id
    with zipfile.ZipFile(archive) as zf:
        infos = [i for i in zf.infolist() if i.filename != MANIFEST_NAME and not i.is_dir()]
        for info in infos:
            if not is_safe_name(info.filename):
                raise SessionFileError(f"unexpected file in session archive: {info.filename!r}")
        target.mkdir(parents=True, exist_ok=True)
        # Same id but different recordings (e.g. from another machine): don't mix them.
        for info in infos:
            dest = target / info.filename
            if info.filename.endswith(".jsonl") and info.filename != CORRECTIONS_NAME and dest.exists():
                with zf.open(info) as src:
                    archived_first = _first_line(src.readline())
                with dest.open("rb") as existing:
                    local_first = _first_line(existing.readline())
                if archived_first and local_first and archived_first != local_first:
                    raise SessionFileError(
                        f"{target} already holds a different session named {session_id}")
        for info in infos:
            dest = target / info.filename
            if dest.exists() and dest.stat().st_size >= info.file_size:
                continue
            fd, tmp = tempfile.mkstemp(prefix=f".{info.filename}.", dir=str(target))
            try:
                with os.fdopen(fd, "wb") as out, zf.open(info) as src:
                    shutil.copyfileobj(src, out, 1024 * 1024)
                os.replace(tmp, dest)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
    write_transcript(target)
    return target


def finalize_session(session_dir: Path, log=None) -> Path | None:
    """Write the transcript and archive at the end of a run; never raises."""
    started = time.monotonic()
    try:
        path = pack_session(session_dir)
    except Exception as exc:
        if log:
            log(f"session files not written for {session_dir}: {exc}")
        return None
    if log:
        log(f"session files written: {path} ({time.monotonic() - started:.1f}s)")
    return path


def refresh_transcript(session_dir: Path, log=None) -> None:
    """Rewrite transcript.txt; never raises (used from the service's hot paths)."""
    try:
        write_transcript(session_dir)
    except Exception as exc:
        if log:
            log(f"transcript not written for {session_dir}: {exc}")
