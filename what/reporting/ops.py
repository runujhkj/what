import sys
from typing import Any

from .format import overall_line, settings_line, suite_better, suite_header, suite_worse
from .types import SuiteResult


def start_suite(reporter: Any, settings: dict[str, Any]) -> None:
    reporter.suite_index += 1
    reporter.current_suite = SuiteResult(settings=settings)
    reporter.last_transcript = ""
    if not reporter.live:
        header = suite_header(reporter.suite_index, reporter.suite_total, settings)
        sys.stdout.write(header + "\n")
    render(reporter)


def case_result(reporter: Any, case_id: str, result: dict[str, Any]) -> None:
    if not reporter.current_suite:
        return
    reporter.current_suite.case_results[case_id] = result
    reporter.case_total_counts[case_id] += 1
    if result.get("pass"):
        reporter.case_pass_counts[case_id] += 1
    if not reporter.live:
        status = "PASS" if result.get("pass") else "FAIL"
        sys.stdout.write(
            f"  {case_id}: {status} wer={result['wer']:.3f} sub={result['sub']} "
            f"ins={result['ins']} del={result['del']} stutter={result['stutter']:.3f} thanks={result['thanks']}\n"
        )
    render(reporter)


def update_transcript(reporter: Any, delta: str) -> None:
    if not delta:
        return
    reporter.last_transcript += (delta + " ")
    if not reporter.live:
        sys.stdout.write(delta + " ")
        sys.stdout.flush()
    render(reporter)


def suite_done(reporter: Any, overall: dict[str, Any]) -> None:
    if not reporter.current_suite:
        return
    reporter.current_suite.overall = overall
    if reporter.best_suite is None or suite_better(reporter.current_suite, reporter.best_suite):
        reporter.best_suite = {
            "settings": reporter.current_suite.settings,
            "overall": overall,
        }
    if reporter.worst_suite is None or suite_worse(reporter.current_suite, reporter.worst_suite):
        reporter.worst_suite = {
            "settings": reporter.current_suite.settings,
            "overall": overall,
        }
    if not reporter.live:
        sys.stdout.write(
            f"  overall: wer={overall['wer']:.3f} sub={overall['sub']} ins={overall['ins']} "
            f"del={overall['del']} stutter={overall['stutter']:.3f} thanks={overall['thanks_for_watching']}\n"
        )
    render(reporter)


def run_done(reporter: Any) -> None:
    if reporter.live:
        render(reporter, final=True)
    summary = summary_lines(reporter)
    sys.stdout.write("\n" + "\n".join(summary) + "\n")


def summary_lines(reporter: Any) -> list[str]:
    lines = []
    if reporter.best_suite:
        lines.append("best settings:")
        lines.append(settings_line(reporter.best_suite["settings"]))
        lines.append(overall_line(reporter.best_suite["overall"]))
    if reporter.worst_suite:
        lines.append("worst settings:")
        lines.append(settings_line(reporter.worst_suite["settings"]))
        lines.append(overall_line(reporter.worst_suite["overall"]))
    lines.append("per-case pass rate:")
    for case_id in reporter.cases:
        total = reporter.case_total_counts[case_id]
        passed = reporter.case_pass_counts[case_id]
        rate = (passed / total) if total else 0.0
        lines.append(f"  {case_id}: {passed}/{total} ({rate:.2f})")
    if reporter.log_path:
        lines.append(f"log: {reporter.log_path}")
    return lines


def render(reporter: Any, final: bool = False) -> None:
    if not reporter.live:
        return
    if not reporter.current_suite:
        return
    sys.stdout.write("\033[H\033[J")
    sys.stdout.write(suite_header(reporter.suite_index, reporter.suite_total, reporter.current_suite.settings) + "\n")
    if reporter.last_transcript:
        sys.stdout.write("live transcript: " + reporter.last_transcript[-400:] + "\n")
    sys.stdout.write("progress:\n")
    for case_id in reporter.cases:
        total = reporter.case_total_counts[case_id]
        passed = reporter.case_pass_counts[case_id]
        sys.stdout.write(f"  {case_id}: {passed}/{total}\n")
    sys.stdout.write("current suite:\n")
    for case_id in reporter.cases:
        result = reporter.current_suite.case_results.get(case_id)
        if not result:
            sys.stdout.write(f"  {case_id}: ...\n")
            continue
        status = "PASS" if result.get("pass") else "FAIL"
        sys.stdout.write(
            f"  {case_id}: {status} wer={result['wer']:.3f} sub={result['sub']} "
            f"ins={result['ins']} del={result['del']} stutter={result['stutter']:.3f} thanks={result['thanks']}\n"
        )
    if reporter.best_suite:
        sys.stdout.write("best so far:\n")
        sys.stdout.write("  " + settings_line(reporter.best_suite["settings"]) + "\n")
        sys.stdout.write("  " + overall_line(reporter.best_suite["overall"]) + "\n")
    if reporter.worst_suite:
        sys.stdout.write("worst so far:\n")
        sys.stdout.write("  " + settings_line(reporter.worst_suite["settings"]) + "\n")
        sys.stdout.write("  " + overall_line(reporter.worst_suite["overall"]) + "\n")
    sys.stdout.flush()
