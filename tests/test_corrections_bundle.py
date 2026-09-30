"""Coverage plan chunk 2: corrections export/import round-trip and jsonl helpers."""
from __future__ import annotations

import json
import os

from what import corrections


def _write(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_read_jsonl_skips_blank_and_malformed_lines(tmp_path):
    p = tmp_path / "c.jsonl"
    p.write_text('{"a": 1}\n\n  \nnot json\n{"b": 2}\n', encoding="utf-8")
    assert corrections.read_jsonl(str(p)) == [{"a": 1}, {"b": 2}]


def test_read_jsonl_missing_file_is_empty(tmp_path):
    assert corrections.read_jsonl(str(tmp_path / "nope.jsonl")) == []


def test_write_then_read_round_trips_unicode(tmp_path):
    rows = [{"text": "café"}, {"text": "naïve"}]
    p = tmp_path / "out.jsonl"
    corrections.write_jsonl(str(p), rows)
    assert corrections.read_jsonl(str(p)) == rows


def test_list_correction_files_filters(tmp_path):
    (tmp_path / "a.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "b.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "export_bundle.jsonl").write_text("", encoding="utf-8")  # excluded
    (tmp_path / "notes.txt").write_text("", encoding="utf-8")            # excluded
    found = {os.path.basename(p) for p in corrections.list_correction_files(str(tmp_path))}
    assert found == {"a.jsonl", "b.jsonl"}


def test_list_correction_files_missing_dir_is_empty(tmp_path):
    assert corrections.list_correction_files(str(tmp_path / "missing")) == []


def test_export_bundle_merges_files_and_collects_speakers(tmp_path):
    src = tmp_path / "corr"
    src.mkdir()
    _write(src / "s1.jsonl", [{"speaker_id": "alice", "text": "one"}])
    _write(src / "s2.jsonl", [{"speaker_id": "bob", "text": "two"}, {"text": "no speaker"}])
    out = tmp_path / "export"

    result = corrections.export_bundle(str(src), str(out), me_speaker_id="alice", notes="n")
    assert result["ok"] is True
    assert result["count"] == 3

    bundle = corrections.read_jsonl(result["bundle"])
    assert len(bundle) == 3
    meta = json.loads((out / "export_meta.json").read_text(encoding="utf-8"))
    assert meta["speakers"] == ["alice", "bob"]  # sorted, deduped, blanks skipped
    assert meta["me_speaker_id"] == "alice"
    assert meta["notes"] == "n"


def test_import_bundle_remaps_speakers_and_keeps_original(tmp_path):
    bundle = tmp_path / "export_bundle.jsonl"
    _write(bundle, [
        {"speaker_id": "alice", "text": "one"},
        {"speaker_id": "carol", "text": "two"},  # not in map -> unchanged
        {"text": "no speaker"},
    ])
    out = tmp_path / "imported"

    result = corrections.import_bundle(str(bundle), str(out), speaker_map={"alice": "me"})
    assert result["ok"] is True and result["count"] == 3

    rows = corrections.read_jsonl(result["imported"])
    assert rows[0]["speaker_id"] == "me"
    assert rows[0]["speaker_id_original"] == "alice"
    assert rows[1]["speaker_id"] == "carol"
    assert "speaker_id_original" not in rows[1]
    assert "speaker_id" not in rows[2]


def test_export_then_import_round_trip(tmp_path):
    src = tmp_path / "corr"
    src.mkdir()
    _write(src / "s.jsonl", [{"speaker_id": "alice", "text": "hello"}])
    exported = corrections.export_bundle(str(src), str(tmp_path / "exp"))
    imported = corrections.import_bundle(exported["bundle"], str(tmp_path / "imp"))
    assert imported["count"] == exported["count"] == 1
