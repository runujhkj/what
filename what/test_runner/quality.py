from .types import WORD_RE


def stutter_score(text: str, window: int = 6) -> float:
    words = WORD_RE.findall(text.lower())
    if len(words) < 2:
        return 0.0
    repeats = 0
    total = 0
    for i in range(len(words)):
        start = max(0, i - window)
        context = words[start:i]
        total += 1
        if words[i] in context:
            repeats += 1
    return repeats / total


def phrase_count(text: str, phrase: str) -> int:
    text_norm = " ".join(WORD_RE.findall(text.lower()))
    phrase_norm = " ".join(WORD_RE.findall(phrase.lower()))
    if not phrase_norm:
        return 0
    return text_norm.count(phrase_norm)
