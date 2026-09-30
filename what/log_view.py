import json
import os
from dataclasses import dataclass
from typing import Any


@dataclass
class LogSummary:
    log_id: int
    path: str
    suites: int
    best: dict[str, Any] | None
    worst: dict[str, Any] | None


def list_logs(log_dir: str = "logs") -> list[str]:
    if not os.path.isdir(log_dir):
        return []
    files = [
        f
        for f in os.listdir(log_dir)
        if (f.startswith("battery-") or f.startswith("test-")) and f.endswith(".jsonl")
    ]
    files.sort()
    return [os.path.join(log_dir, f) for f in files]


def summarize_log(path: str) -> LogSummary:
    suites = 0
    best = None
    worst = None
    with open(path, "r", encoding="ascii") as f:
        for line in f:
            if not line.strip():
                continue
            suite = json.loads(line)
            suites += 1
            overall = suite.get("overall", {})
            if "pass_rate" not in overall:
                pass_rate = _pass_rate(suite)
                overall["pass_rate"] = pass_rate
            entry = {"settings": suite.get("settings", {}), "overall": overall}
            if best is None or _better(entry, best):
                best = entry
            if worst is None or _worse(entry, worst):
                worst = entry
    return LogSummary(log_id=0, path=path, suites=suites, best=best, worst=worst)


def print_history(count: int) -> None:
    logs = list_logs()
    if not logs:
        print("no logs")
        return
    tail = logs[-count:]
    for idx, path in enumerate(tail, start=len(logs) - len(tail) + 1):
        summary = summarize_log(path)
        summary.log_id = idx
        best = summary.best or {}
        best_overall = best.get("overall", {})
        print(
            f"id={summary.log_id} file={os.path.basename(path)} suites={summary.suites} "
            f"best_wer={best_overall.get('wer', 0):.3f} best_pass={best_overall.get('pass_rate', 0):.2f}"
        )


def print_log_by_id(log_id: int) -> None:
    logs = list_logs()
    if log_id < 1 or log_id > len(logs):
        print("log id not found")
        return
    _print_log(logs[log_id - 1], log_id)


def print_last() -> None:
    logs = list_logs()
    if not logs:
        print("no logs")
        return
    _print_log(logs[-1], len(logs))


def _print_log(path: str, log_id: int) -> None:
    summary = summarize_log(path)
    summary.log_id = log_id
    print(f"log id={summary.log_id} file={os.path.basename(path)} suites={summary.suites}")
    if summary.best:
        print("best settings:")
        print("  " + _settings_line(summary.best["settings"]))
        print("  " + _overall_line(summary.best["overall"]))
    if summary.worst:
        print("worst settings:")
        print("  " + _settings_line(summary.worst["settings"]))
        print("  " + _overall_line(summary.worst["overall"]))


def _pass_rate(suite: dict[str, Any]) -> float:
    cases = suite.get("cases", [])
    if not cases:
        return 0.0
    passed = sum(1 for c in cases if c.get("pass"))
    return passed / len(cases)


def _better(current: dict[str, Any], best: dict[str, Any]) -> bool:
    c = current["overall"]
    b = best["overall"]
    if c.get("pass_rate") != b.get("pass_rate"):
        return c.get("pass_rate", 0) > b.get("pass_rate", 0)
    return c.get("wer", 1.0) < b.get("wer", 1.0)


def _worse(current: dict[str, Any], worst: dict[str, Any]) -> bool:
    c = current["overall"]
    w = worst["overall"]
    if c.get("pass_rate") != w.get("pass_rate"):
        return c.get("pass_rate", 0) < w.get("pass_rate", 0)
    return c.get("wer", 0.0) > w.get("wer", 0.0)


def _settings_line(settings: dict[str, Any]) -> str:
    return (
        f"model={settings.get('model_size')} beam={settings.get('beam_size')} "
        f"ns={settings.get('no_speech_threshold')} vad={settings.get('vad_mode')}/{settings.get('vad_speech_ratio')} "
        f"overlap={settings.get('overlap_ms')} chunk={settings.get('chunk_ms')} cond_prev={settings.get('condition_on_previous_text')}"
    )


def _overall_line(overall: dict[str, Any]) -> str:
    return (
        f"wer={overall.get('wer', 0):.3f} pass_rate={overall.get('pass_rate', 0):.2f} "
        f"sub={overall.get('sub', 0)} ins={overall.get('ins', 0)} del={overall.get('del', 0)}"
    )
