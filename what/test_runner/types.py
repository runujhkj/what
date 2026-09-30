import re
from dataclasses import dataclass


WORD_RE = re.compile(r"[a-z0-9']+")


@dataclass
class Case:
    case_id: str
    audio: str
    text: str
