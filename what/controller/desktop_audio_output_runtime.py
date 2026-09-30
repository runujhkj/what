from __future__ import annotations

import json
import subprocess
from pathlib import Path


def routing_receipt_path(state_dir: Path) -> Path:
    return state_dir / "desktop-audio-routing-receipt.json"


def read_receipt(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_receipt(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def coreaudio_helper_path(repo_root: Path) -> Path:
    return repo_root / "bin" / "what-coreaudio-aggregate"


def list_output_rows(repo_root: Path) -> list[dict]:
    helper = coreaudio_helper_path(repo_root)
    if not helper.exists():
        return []
    try:
        proc = subprocess.run(
            [str(helper), "list-outputs"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return []
    out = str(proc.stdout or "").strip()
    payload = {}
    if out:
        lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
        candidates = [out]
        if lines:
            candidates.append(lines[-1])
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except Exception:
                continue
            if isinstance(parsed, dict):
                payload = parsed
                break
    rows = payload.get("outputs", []) if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        return []
    out_rows: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        lower = name.lower()
        kind = "physical"
        if "blackhole" in lower or "loopback" in lower or "soundflower" in lower or "vb-cable" in lower:
            kind = "loopback"
        elif "what-desktop" in lower or lower.startswith("what-"):
            kind = "aggregate"
        out_rows.append(
            {
                "name": name,
                "kind": kind,
                "selectable": kind == "physical",
            }
        )
    return out_rows


def select_output(*, state_dir: Path, output_name: str) -> dict:
    value = str(output_name or "").strip()
    if not value:
        return {"ok": False, "error": "missing_output_name"}
    path = routing_receipt_path(state_dir)
    receipt = read_receipt(path)
    receipt["selected_output"] = value
    write_receipt(path, receipt)
    return {"ok": True, "selected_output": value}

