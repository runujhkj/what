import json
import os
from typing import Iterable

from .types import Case


def load_cases(path: str) -> list[Case]:
    with open(path, "r", encoding="ascii") as f:
        data = json.load(f)
    cases = []
    for entry in data:
        cases.append(
            Case(
                case_id=entry["id"],
                audio=entry["audio"],
                text=entry["text"],
            )
        )
    return cases


def select_cases(cases: Iterable[Case], files: list[str] | None) -> list[Case]:
    if not files:
        return list(cases)
    selected: list[Case] = []
    case_map = {case.case_id: case for case in cases}
    audio_map = {os.path.normpath(case.audio): case for case in cases}

    for path in files:
        norm = os.path.normpath(path)
        case = audio_map.get(norm)
        if not case:
            stem = os.path.splitext(os.path.basename(path))[0]
            case = case_map.get(stem)
        if not case:
            raise ValueError(f"No test case found for file: {path}")
        selected.append(case)
    return selected
