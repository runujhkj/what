"""Coverage plan chunk 3: battery/test log listing and summary rendering."""
from __future__ import annotations

import json
import os

from what import log_view


def _settings(**over):
    base = dict(
        model_size="medium", beam_size=1, no_speech_threshold=0.5, vad_mode=3,
        vad_speech_ratio=0.2, overlap_ms=0, chunk_ms=2500, condition_on_previous_text=False,
    )
    base.update(over)
    return base


def _write_log(path, suites):
    path.write_text("".join(json.dumps(s) + "\n" for s in suites), encoding="ascii")


def test_list_logs_filters_and_sorts(tmp_path):
    (tmp_path / "battery-2.jsonl").write_text("", encoding="ascii")
    (tmp_path / "battery-1.jsonl").write_text("", encoding="ascii")
    (tmp_path / "test-3.jsonl").write_text("", encoding="ascii")
    (tmp_path / "notes.txt").write_text("", encoding="ascii")       # wrong extension
    (tmp_path / "battery-x.log").write_text("", encoding="ascii")   # wrong extension
    (tmp_path / "run-9.jsonl").write_text("", encoding="ascii")     # wrong prefix

    names = [os.path.basename(p) for p in log_view.list_logs(str(tmp_path))]
    assert names == ["battery-1.jsonl", "battery-2.jsonl", "test-3.jsonl"]


def test_list_logs_missing_dir(tmp_path):
    assert log_view.list_logs(str(tmp_path / "gone")) == []


def test_summarize_log_picks_best_and_worst(tmp_path):
    log = tmp_path / "battery-1.jsonl"
    _write_log(log, [
        {"settings": _settings(), "overall": {"wer": 0.1, "pass_rate": 1.0}},
        # No pass_rate in overall -> derived from the case list (0.5).
        {"settings": _settings(model_size="weak"),
         "cases": [{"pass": True}, {"pass": False}],
         "overall": {"wer": 0.4}},
    ])
    summary = log_view.summarize_log(str(log))
    assert summary.suites == 2
    assert summary.best["overall"]["pass_rate"] == 1.0
    assert summary.worst["overall"]["pass_rate"] == 0.5
    assert summary.worst["settings"]["model_size"] == "weak"


def test_print_last_renders_best_and_worst(tmp_path, monkeypatch, capsys):
    log = tmp_path / "battery-1.jsonl"
    _write_log(log, [
        {"settings": _settings(), "overall": {"wer": 0.1, "pass_rate": 1.0, "sub": 2}},
        {"settings": _settings(model_size="weak"), "overall": {"wer": 0.4, "pass_rate": 0.3}},
    ])
    monkeypatch.setattr(log_view, "list_logs", lambda *a, **k: [str(log)])
    log_view.print_last()
    out = capsys.readouterr().out
    assert "best settings:" in out and "worst settings:" in out
    assert "model=medium" in out
    assert "wer=0.100" in out and "pass_rate=1.00" in out


def test_print_history_lists_tail(tmp_path, monkeypatch, capsys):
    logs = []
    for i in (1, 2, 3):
        p = tmp_path / f"battery-{i}.jsonl"
        _write_log(p, [{"settings": _settings(), "overall": {"wer": 0.1 * i, "pass_rate": 1.0}}])
        logs.append(str(p))
    monkeypatch.setattr(log_view, "list_logs", lambda *a, **k: logs)
    log_view.print_history(2)
    out = capsys.readouterr().out
    # Only the last two logs (ids 2 and 3) are shown.
    assert "id=2" in out and "id=3" in out
    assert "id=1" not in out


def test_print_log_by_id_out_of_range(monkeypatch, capsys):
    monkeypatch.setattr(log_view, "list_logs", lambda *a, **k: [])
    log_view.print_log_by_id(5)
    assert "log id not found" in capsys.readouterr().out


def test_print_last_no_logs(monkeypatch, capsys):
    monkeypatch.setattr(log_view, "list_logs", lambda *a, **k: [])
    log_view.print_last()
    assert "no logs" in capsys.readouterr().out


def test_print_history_no_logs(monkeypatch, capsys):
    monkeypatch.setattr(log_view, "list_logs", lambda *a, **k: [])
    log_view.print_history(3)
    assert "no logs" in capsys.readouterr().out
