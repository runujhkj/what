import json
import subprocess
import sys
import wave
import zipfile
from datetime import timezone
from pathlib import Path

import pytest

from what.session_files import (
    SessionFileError,
    archive_path,
    pack_session,
    read_manifest,
    render_transcript,
    session_segments,
    unpack_session,
)

SESSION = "2026-09-18_007_T103758"
T0 = 1_758_191_878.0  # 2025-09-18T10:37:58Z


def _event(client_id, source, segments, *, anchor=T0, chunk_end=None, wall_time=None):
    event = {
        "type": "segment", "session_id": SESSION, "client_id": client_id,
        "input_source_id": source, "chunk_index": 0,
        "chunk_start": segments[0][1] if segments else 0.0,
        "chunk_end": chunk_end if chunk_end is not None else (segments[-1][2] if segments else 0.0),
        "text": " ".join(s[3] for s in segments),
        "segments": [
            {"id": sid, "abs_start": start, "abs_end": end, "text": " " + text}
            for sid, start, end, text in segments
        ],
    }
    if anchor is not None:
        event["stream_started_at"] = anchor
    if wall_time is not None:
        event["wall_time"] = wall_time
    return event


def _write_log(session_dir, client_id, events, wav_seconds=0.5):
    session_dir.mkdir(parents=True, exist_ok=True)
    with (session_dir / f"{client_id}.jsonl").open("a", encoding="utf-8") as fh:
        for event in events:
            fh.write(json.dumps(event) + "\n")
    with wave.open(str(session_dir / f"{client_id}.wav"), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * int(16000 * wav_seconds))


def _correction(client_id, segment_id, revision, text):
    return {
        "schema": "what.correction.v1", "session_id": SESSION, "client_id": client_id,
        "segment_ids": [segment_id], "revision": revision,
        "edit_type": "replace" if text else "delete", "corrected_text": text,
    }


@pytest.fixture
def session(tmp_path):
    d = tmp_path / "logs" / SESSION
    # Mic starts at T0; desktop's recording started 2 s later, so its offsets are shifted.
    _write_log(d, "mic-aaaa1111", [
        _event("mic-aaaa1111", "mic", [("e0-s1", 1.0, 2.0, "Hello there."),
                                       ("e0-s2", 2.5, 3.0, "How are you?")]),
        _event("mic-aaaa1111", "mic", [("e0-s3", 20.0, 21.0, "Back again.")]),
    ])
    _write_log(d, "desktop-bbbb2222", [
        _event("desktop-bbbb2222", "desktop", [("e0-s1", 3.0, 4.0, "I'm fine, thanks.")],
               anchor=T0 + 2.0),
    ])
    return d


def test_segments_are_merged_across_sources_in_wall_clock_order(session):
    segs = session_segments(session)
    assert [(s.source, s.text) for s in segs] == [
        ("mic", "Hello there."),
        ("mic", "How are you?"),
        ("desktop", "I'm fine, thanks."),  # desktop 3.0 s after its own start = T0 + 5
        ("mic", "Back again."),
    ]
    assert segs[2].start == pytest.approx(T0 + 5.0)


def test_transcript_groups_by_source_and_labels_each_block(session):
    text = render_transcript(session, tz=timezone.utc)
    assert text.splitlines()[0] == f"What transcript: session {SESSION}"
    assert "Sources: Desktop (desktop-bbbb2222); Mic (mic-aaaa1111)" in text
    blocks = text.split("\n\n")[1:]
    assert blocks == [
        "[10:37:59 - 10:38:01] Mic\n    Hello there. How are you?",
        "[10:38:03 - 10:38:04] Desktop\n    I'm fine, thanks.",
        "[10:38:18 - 10:38:19] Mic\n    Back again.\n",
    ]


def test_corrections_replace_or_delete_segments(session):
    with (session / "corrections.jsonl").open("w") as fh:
        fh.write(json.dumps(_correction("mic-aaaa1111", "e0-s1", 1, "Hi there.")) + "\n")
        fh.write(json.dumps(_correction("mic-aaaa1111", "e0-s1", 2, "Hello, there.")) + "\n")
        fh.write(json.dumps(_correction("desktop-bbbb2222", "e0-s1", 1, "")) + "\n")
        fh.write("{cut short by a crash\n")
    text = render_transcript(session, tz=timezone.utc)
    assert "[10:37:59 - 10:38:01] Mic (edited)\n    Hello, there. How are you?" in text
    assert "Desktop\n" not in text.split("\n\n", 1)[1]
    assert "Blocks marked (edited)" in text


def test_older_logs_without_an_anchor_are_ordered_by_wall_time(tmp_path):
    d = tmp_path / SESSION
    # Written just after each chunk ended: wall_time - chunk_end gives the recording start.
    _write_log(d, "mic-old", [_event("mic-old", "mic", [("s1", 10.0, 11.0, "later")],
                                     anchor=None, chunk_end=11.0, wall_time=T0 + 11.2)])
    _write_log(d, "desktop-old", [_event("desktop-old", "desktop", [("s1", 1.0, 2.0, "earlier")],
                                         anchor=None, chunk_end=2.0, wall_time=T0 + 2.1)])
    assert [s.text for s in session_segments(d)] == ["earlier", "later"]


def test_empty_session_says_so(tmp_path):
    d = tmp_path / SESSION
    d.mkdir()
    assert "No transcribed speech in this session." in render_transcript(d)


def test_pack_writes_transcript_and_a_self_contained_archive(session):
    (session / "process.log").write_text("2026-09-18T10:37:58 started\n")
    path = pack_session(session)
    assert path == archive_path(session) == session / f"{SESSION}.what"
    assert (session / "transcript.txt").exists()
    manifest = read_manifest(path)
    assert manifest["session_id"] == SESSION
    assert {(s["source"], s["transcript"], s["recording"]) for s in manifest["sources"]} == {
        ("mic", "mic-aaaa1111.jsonl", "mic-aaaa1111.wav"),
        ("desktop", "desktop-bbbb2222.jsonl", "desktop-bbbb2222.wav"),
    }
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
    assert names == {"manifest.json", "mic-aaaa1111.jsonl", "mic-aaaa1111.wav",
                     "desktop-bbbb2222.jsonl", "desktop-bbbb2222.wav",
                     "transcript.txt", "process.log"}
    # Packing again replaces the archive rather than nesting it.
    pack_session(session)
    with zipfile.ZipFile(path) as zf:
        assert f"{SESSION}.what" not in zf.namelist()


def test_pack_can_also_copy_the_archive_elsewhere(session, tmp_path):
    out = tmp_path / "shared" / "meeting.what"
    out.parent.mkdir()
    pack_session(session, copy_to=out)
    assert out.read_bytes() == archive_path(session).read_bytes()


def test_unpack_restores_the_session_on_another_machine(session, tmp_path):
    archive = pack_session(session)
    other_logs = tmp_path / "other-machine" / "logs"
    restored = unpack_session(archive, other_logs)
    assert restored == other_logs / SESSION
    for name in ("mic-aaaa1111.jsonl", "mic-aaaa1111.wav", "desktop-bbbb2222.wav"):
        assert (restored / name).read_bytes() == (session / name).read_bytes()
    assert (restored / "transcript.txt").read_text() == (session / "transcript.txt").read_text()


def test_unpack_keeps_newer_local_files(session, tmp_path):
    archive = pack_session(session)
    # Recording continued after the archive was written: the local log is a superset.
    _write_log(session, "mic-aaaa1111", [
        _event("mic-aaaa1111", "mic", [("e0-s4", 30.0, 31.0, "Recorded after packing.")])])
    before = (session / "mic-aaaa1111.jsonl").read_bytes()
    unpack_session(archive, session.parent)
    assert (session / "mic-aaaa1111.jsonl").read_bytes() == before
    assert "Recorded after packing." in (session / "transcript.txt").read_text()


def test_unpack_refuses_a_different_session_with_the_same_id(session, tmp_path):
    archive = pack_session(session)
    elsewhere = tmp_path / "elsewhere"
    _write_log(elsewhere / SESSION, "mic-aaaa1111",
               [_event("mic-aaaa1111", "mic", [("e0-s1", 1.0, 2.0, "Something else entirely.")])])
    with pytest.raises(SessionFileError, match="different session"):
        unpack_session(archive, elsewhere)


def test_unpack_rejects_files_that_are_not_session_archives(tmp_path):
    bogus = tmp_path / "x.what"
    bogus.write_text("not a zip")
    with pytest.raises(SessionFileError):
        unpack_session(bogus, tmp_path / "logs")
    evil = tmp_path / "evil.what"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("manifest.json", json.dumps(
            {"format": "what.session", "version": 1, "session_id": SESSION, "sources": []}))
        zf.writestr("../escape.jsonl", "{}\n")
    with pytest.raises(SessionFileError, match="unexpected file"):
        unpack_session(evil, tmp_path / "logs")
    assert not (tmp_path / "escape.jsonl").exists()
    newer = tmp_path / "newer.what"
    with zipfile.ZipFile(newer, "w") as zf:
        zf.writestr("manifest.json", json.dumps(
            {"format": "what.session", "version": 99, "session_id": SESSION}))
    with pytest.raises(SessionFileError, match="newer version"):
        unpack_session(newer, tmp_path / "logs")


def test_cli_pack_and_unpack_print_json(session, tmp_path):
    run = lambda *args: subprocess.run(  # noqa: E731
        [sys.executable, "-m", "what", "session", *args, "--json"],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1])
    packed = run("pack", str(session))
    assert packed.returncode == 0, packed.stderr
    archive = json.loads(packed.stdout)["path"]
    unpacked = run("unpack", archive, "--logs-dir", str(tmp_path / "restored"))
    assert unpacked.returncode == 0, unpacked.stderr
    result = json.loads(unpacked.stdout)
    assert result == {"ok": True, "session_id": SESSION,
                      "session_dir": str(tmp_path / "restored" / SESSION)}
    failed = run("unpack", str(tmp_path / "missing.what"))
    assert failed.returncode == 1
    assert json.loads(failed.stdout)["ok"] is False
