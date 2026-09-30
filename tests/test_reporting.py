"""Coverage plan chunk 3: reporting format helpers and the RunReporter flow."""
from __future__ import annotations

from what.reporting.format import (
    overall_line,
    settings_line,
    suite_better,
    suite_header,
    suite_worse,
)
from what.reporting.runner import RunReporter
from what.reporting.types import SuiteResult


def _settings(**over):
    base = dict(
        model_size="medium", beam_size=1, no_speech_threshold=0.5, vad_mode=3,
        vad_speech_ratio=0.2, overlap_ms=0, chunk_ms=2500, condition_on_previous_text=False,
    )
    base.update(over)
    return base


def _overall(wer=0.1, pass_rate=1.0, sub=1, ins=0, dele=0, stutter=0.0, thanks=0):
    return {"wer": wer, "pass_rate": pass_rate, "sub": sub, "ins": ins, "del": dele,
            "stutter": stutter, "thanks_for_watching": thanks}


def _case(passed=True, wer=0.1):
    return {"pass": passed, "wer": wer, "sub": 1, "ins": 0, "del": 0, "stutter": 0.0, "thanks": 0}


# --- format.py ---------------------------------------------------------------

def test_suite_header_and_settings_line():
    header = suite_header(1, 3, _settings())
    assert header.startswith("[1/3]")
    assert "model=medium" in header and "chunk=2500" in header
    assert "model=medium" in settings_line(_settings())


def test_overall_line_formats_floats():
    line = overall_line(_overall(wer=0.125, stutter=0.5))
    assert "wer=0.125" in line and "stutter=0.500" in line and "thanks=0" in line


def test_suite_better_prefers_higher_pass_rate_then_lower_wer():
    cur = SuiteResult(settings=_settings(), overall=_overall(pass_rate=0.9, wer=0.3))
    assert suite_better(cur, {"overall": _overall(pass_rate=0.5, wer=0.1)}) is True
    # Equal pass rate -> lower WER wins.
    cur_eq = SuiteResult(settings=_settings(), overall=_overall(pass_rate=0.5, wer=0.1))
    assert suite_better(cur_eq, {"overall": _overall(pass_rate=0.5, wer=0.2)}) is True
    assert suite_better(cur_eq, {"overall": _overall(pass_rate=0.5, wer=0.05)}) is False


def test_suite_worse_prefers_lower_pass_rate_then_higher_wer():
    cur = SuiteResult(settings=_settings(), overall=_overall(pass_rate=0.2, wer=0.1))
    assert suite_worse(cur, {"overall": _overall(pass_rate=0.8, wer=0.1)}) is True
    cur_eq = SuiteResult(settings=_settings(), overall=_overall(pass_rate=0.5, wer=0.4))
    assert suite_worse(cur_eq, {"overall": _overall(pass_rate=0.5, wer=0.2)}) is True


# --- ops.py via RunReporter --------------------------------------------------

def _reporter():
    # live=False regardless (pytest stdout is not a tty), exercising the plain-text branch.
    return RunReporter("battery", ["c1", "c2"], suite_total=2, live=False, log_path="run.jsonl")


def test_full_run_tracks_best_worst_and_counts(capsys):
    r = _reporter()
    r.start_suite(_settings(model_size="good"))
    r.case_result("c1", _case(True))
    r.case_result("c2", _case(True))
    r.update_transcript("hello world")
    r.suite_done(_overall(pass_rate=1.0, wer=0.1))

    r.start_suite(_settings(model_size="bad"))
    r.case_result("c1", _case(False))
    r.case_result("c2", _case(False))
    r.suite_done(_overall(pass_rate=0.0, wer=0.6))

    r.run_done()

    assert r.best_suite["overall"]["pass_rate"] == 1.0
    assert r.best_suite["settings"]["model_size"] == "good"
    assert r.worst_suite["overall"]["pass_rate"] == 0.0
    assert r.case_total_counts["c1"] == 2
    assert r.case_pass_counts["c1"] == 1  # passed suite 1, failed suite 2

    out = capsys.readouterr().out
    assert "best settings:" in out and "worst settings:" in out
    assert "per-case pass rate:" in out
    assert "log: run.jsonl" in out


def test_case_result_and_suite_done_no_op_without_active_suite():
    r = _reporter()
    # No start_suite called: these must be safe no-ops, not crashes.
    r.case_result("c1", _case(True))
    r.suite_done(_overall())
    assert r.current_suite is None
    assert r.best_suite is None


def test_live_render_emits_ansi_and_progress(capsys):
    r = _reporter()
    r.start_suite(_settings())
    r.case_result("c1", _case(True))
    r.live = True  # force the live render branch
    r._render()
    out = capsys.readouterr().out
    assert "\033[H\033[J" in out  # clear screen
    assert "progress:" in out and "current suite:" in out
