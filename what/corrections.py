from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass


@dataclass
class ExportMeta:
    recorded_at: str
    me_speaker_id: str
    speakers: list[str]
    instance_id: str
    notes: str


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def list_correction_files(root: str) -> list[str]:
    if not os.path.isdir(root):
        return []
    return [
        os.path.join(root, name)
        for name in os.listdir(root)
        if name.endswith(".jsonl") and name not in {"export_bundle.jsonl"}
    ]


def read_jsonl(path: str) -> list[dict]:
    items: list[dict] = []
    if not os.path.exists(path):
        return items
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return items


def write_jsonl(path: str, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def export_bundle(
    corrections_dir: str,
    export_dir: str,
    me_speaker_id: str = "me",
    instance_id: str = "default",
    notes: str = "",
) -> dict:
    os.makedirs(export_dir, exist_ok=True)
    rows: list[dict] = []
    speakers: set[str] = set()
    for path in list_correction_files(corrections_dir):
        rows.extend(read_jsonl(path))
    for row in rows:
        spk = row.get("speaker_id")
        if spk:
            speakers.add(spk)
    meta = ExportMeta(
        recorded_at=_now_iso(),
        me_speaker_id=me_speaker_id or "me",
        speakers=sorted(speakers),
        instance_id=instance_id or "default",
        notes=notes,
    )
    bundle_path = os.path.join(export_dir, "export_bundle.jsonl")
    meta_path = os.path.join(export_dir, "export_meta.json")
    write_jsonl(bundle_path, rows)
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(meta.__dict__, fh, indent=2)
    return {"ok": True, "bundle": bundle_path, "meta": meta_path, "count": len(rows)}


def import_bundle(
    bundle_path: str,
    out_dir: str,
    speaker_map: dict[str, str] | None = None,
) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    rows = read_jsonl(bundle_path)
    mapping = speaker_map or {}
    updated: list[dict] = []
    for row in rows:
        if "speaker_id" in row:
            original = row.get("speaker_id")
            if original in mapping:
                row["speaker_id_original"] = original
                row["speaker_id"] = mapping[original]
        updated.append(row)
    out_path = os.path.join(out_dir, "imported.jsonl")
    write_jsonl(out_path, updated)
    return {"ok": True, "imported": out_path, "count": len(updated)}
