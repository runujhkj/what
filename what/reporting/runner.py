import sys
from typing import Any

from .ops import case_result, render, run_done, start_suite, suite_done, update_transcript


class RunReporter:
    def __init__(
        self,
        run_type: str,
        cases: list[str],
        suite_total: int,
        live: bool = True,
        log_path: str | None = None,
    ) -> None:
        self.run_type = run_type
        self.cases = cases
        self.suite_total = suite_total
        self.live = live and sys.stdout.isatty()
        self.log_path = log_path
        self.suite_index = 0
        self.current_suite = None
        self.case_pass_counts = {case_id: 0 for case_id in cases}
        self.case_total_counts = {case_id: 0 for case_id in cases}
        self.best_suite: dict[str, Any] | None = None
        self.worst_suite: dict[str, Any] | None = None
        self.last_transcript = ""

    def start_suite(self, settings: dict[str, Any]) -> None:
        start_suite(self, settings)

    def case_result(self, case_id: str, result: dict[str, Any]) -> None:
        case_result(self, case_id, result)

    def update_transcript(self, delta: str) -> None:
        update_transcript(self, delta)

    def suite_done(self, overall: dict[str, Any]) -> None:
        suite_done(self, overall)

    def run_done(self) -> None:
        run_done(self)

    def _render(self, final: bool = False) -> None:
        render(self, final)
