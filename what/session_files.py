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
  can be reopened (viewed, edited, replayed, continued) on this or another machine. Recordings
  are stored as FLAC (lossless) when FFmpeg is available, else as the WAV itself.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
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


WAV_HEADER_BYTES = 44


def _ffmpeg() -> str | None:
    return os.environ.get("WHAT_FFMPEG") or shutil.which("ffmpeg")


def _pcm_wav_format(path: Path) -> tuple[int, int] | None:
    """(sample_rate, channels) of a canonical 44-byte-header 16-bit PCM WAV, as the service
    writes (what/service/recording.py); None for anything else."""
    try:
        with path.open("rb") as fh:
            header = fh.read(WAV_HEADER_BYTES)
    except OSError:
        return None
    if (len(header) < WAV_HEADER_BYTES or header[0:4] != b"RIFF" or header[8:16] != b"WAVEfmt "
            or int.from_bytes(header[16:20], "little") != 16 or header[36:40] != b"data"):
        return None
    audio_format = int.from_bytes(header[20:22], "little")
    channels = int.from_bytes(header[22:24], "little")
    sample_rate = int.from_bytes(header[24:28], "little")
    bits = int.from_bytes(header[34:36], "little")
    if audio_format != 1 or bits != 16 or channels < 1 or sample_rate < 1:
        return None
    return sample_rate, channels


def _encode_flac(ffmpeg: str, wav: Path, out: Path, sample_rate: int, channels: int) -> int:
    """Encode the WAV's PCM to FLAC; returns the number of PCM bytes encoded.

    The PCM is fed through stdin, sized from the file length rather than the header: a
    recording that is still being written has a header that lags its data.
    """
    frame_bytes = 2 * channels
    pcm_bytes = (wav.stat().st_size - WAV_HEADER_BYTES) // frame_bytes * frame_bytes
    proc = subprocess.Popen(
        [ffmpeg, "-nostdin", "-hide_banner", "-v", "error", "-y",
         "-f", "s16le", "-ar", str(sample_rate), "-ac", str(channels), "-i", "pipe:0",
         "-c:a", "flac", "-f", "flac", str(out)],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    assert proc.stdin is not None
    try:
        with wav.open("rb") as fh:
            fh.seek(WAV_HEADER_BYTES)
            remaining = pcm_bytes
            while remaining > 0:
                chunk = fh.read(min(remaining, 1024 * 1024))
                if not chunk:
                    break
                proc.stdin.write(chunk)
                remaining -= len(chunk)
        proc.stdin.close()
    except BrokenPipeError:
        pass
    stderr = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
    if proc.wait() != 0:
        raise SessionFileError(f"FLAC encoding failed for {wav.name}: {stderr.strip()[-300:]}")
    return pcm_bytes - remaining


def _decode_flac(ffmpeg: str, flac: Path, wav: Path, sample_rate: int, channels: int) -> int:
    """Decode FLAC to a canonical 44-byte-header WAV (the layout replay and the service
    expect); returns the number of PCM bytes written."""
    import wave

    proc = subprocess.Popen(
        [ffmpeg, "-nostdin", "-hide_banner", "-v", "error", "-i", str(flac),
         "-f", "s16le", "-ar", str(sample_rate), "-ac", str(channels), "pipe:1"],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdout is not None
    written = 0
    with wave.open(str(wav), "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(2)
        out.setframerate(sample_rate)
        while True:
            chunk = proc.stdout.read(1024 * 1024)
            if not chunk:
                break
            out.writeframesraw(chunk)
            written += len(chunk)
    stderr = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
    if proc.wait() != 0:
        raise SessionFileError(f"FLAC decoding failed for {flac.name}: {stderr.strip()[-300:]}")
    return written


def build_manifest(session_dir: Path) -> dict[str, Any]:
    session_dir = Path(session_dir)
    sources = []
    for log in client_logs(session_dir):
        first = next(_read_jsonl(log), None) or {}
        client_id = str(first.get("client_id") or log.stem)
        wav = log.with_suffix(".wav")
        entry: dict[str, Any] = {
            "client_id": client_id,
            "source": source_of(first, client_id),
            "transcript": log.name,
            # The recording's name in the session folder (always .wav), and the member of the
            # archive that holds it ("recording_file"; set by pack_session).
            "recording": wav.name if wav.exists() else None,
        }
        sources.append(entry)

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


STALE_TEMP_SEC = 3600


def _remove_stale_temp_files(folder: Path, name: str) -> None:
    # A pack cut short (the app killed mid-write) leaves ".<name>.<random>" behind, as large
    # as the recordings. Old ones are safe to remove; a recent one may belong to a pack that
    # is still running.
    cutoff = time.time() - STALE_TEMP_SEC
    for tmp in folder.glob(f".{name}.*"):
        try:
            if tmp.stat().st_mtime < cutoff:
                tmp.unlink()
        except OSError:
            pass


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
    target = archive_path(session_dir)
    _remove_stale_temp_files(session_dir, target.name)
    fd, tmp = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(session_dir))
    os.close(fd)
    scratch = Path(tempfile.mkdtemp(prefix=".pack-", dir=str(session_dir)))
    ffmpeg = _ffmpeg()
    try:
        # (archive member name, file on disk, zip compression)
        members: list[tuple[str, Path, int]] = []
        for source in manifest["sources"]:
            members.append((source["transcript"], session_dir / source["transcript"], zipfile.ZIP_DEFLATED))
            if not source["recording"]:
                continue
            wav = session_dir / source["recording"]
            fmt = _pcm_wav_format(wav)
            if ffmpeg and fmt:
                flac_name = Path(source["recording"]).with_suffix(".flac").name
                pcm_bytes = _encode_flac(ffmpeg, wav, scratch / flac_name, *fmt)
                source.update(recording_file=flac_name, recording_codec="flac",
                              sample_rate=fmt[0], channels=fmt[1],
                              recording_bytes=WAV_HEADER_BYTES + pcm_bytes)
                members.append((flac_name, scratch / flac_name, zipfile.ZIP_STORED))
            else:
                # No FFmpeg (or an unexpected WAV layout): store the WAV itself. PCM barely
                # deflates, so storing keeps packing fast.
                source.update(recording_file=source["recording"], recording_codec="pcm",
                              recording_bytes=wav.stat().st_size)
                members.append((source["recording"], wav, zipfile.ZIP_STORED))
        for key in ("corrections", "transcript", "process_log"):
            if manifest[key]:
                members.append((manifest[key], session_dir / manifest[key], zipfile.ZIP_DEFLATED))
        with zipfile.ZipFile(tmp, "w", allowZip64=True) as zf:
            zf.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2) + "\n",
                        compress_type=zipfile.ZIP_DEFLATED)
            for arcname, path, kind in members:
                zf.write(path, arcname=arcname, compress_type=kind)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
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
    version = manifest.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise SessionFileError(f"not a What session file: {archive} (bad version)")
    if version > ARCHIVE_VERSION:
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
    # FLAC members are decoded back to the session folder's .wav (see pack_session).
    encoded: dict[str, dict[str, Any]] = {}
    for source in manifest.get("sources") or []:
        if not isinstance(source, dict) or source.get("recording_codec") != "flac":
            continue
        names = (str(source.get("recording_file") or ""), str(source.get("recording") or ""))
        if not all(is_safe_name(n) for n in names) or not names[1].endswith(".wav"):
            raise SessionFileError(f"invalid recording entry in {archive}")
        encoded[names[0]] = source
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
            if info.filename in encoded:
                _restore_flac(zf, info, target, encoded[info.filename])
                continue
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


def _restore_flac(zf: zipfile.ZipFile, info: zipfile.ZipInfo, target: Path,
                  source: dict[str, Any]) -> None:
    dest = target / str(source["recording"])
    expected = int(source.get("recording_bytes") or 0)
    if dest.exists() and dest.stat().st_size >= expected:
        return  # the local recording is the same or longer
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        raise SessionFileError(
            "FFmpeg is needed to open this session's recordings (install it, or put it on PATH)")
    scratch = Path(tempfile.mkdtemp(prefix=".unpack-", dir=str(target)))
    try:
        flac = scratch / info.filename
        with zf.open(info) as src, flac.open("wb") as out:
            shutil.copyfileobj(src, out, 1024 * 1024)
        wav = scratch / dest.name
        written = _decode_flac(ffmpeg, flac, wav, int(source.get("sample_rate") or 16000),
                               int(source.get("channels") or 1))
        # Lossless round trip: anything else means a damaged file, not a usable recording.
        if expected and WAV_HEADER_BYTES + written != expected:
            raise SessionFileError(
                f"{info.filename} decoded to {written} bytes of audio, expected {expected - WAV_HEADER_BYTES}")
        os.replace(wav, dest)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


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
