from dataclasses import dataclass, field
from typing import Any


@dataclass
class SuiteResult:
    settings: dict[str, Any]
    case_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    overall: dict[str, Any] = field(default_factory=dict)
