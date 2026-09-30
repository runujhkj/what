"""Filter for Whisper's canned near-silence hallucinations.

On silent or low-signal audio, both faster-whisper and WhisperKit sometimes emit a
YouTube-style filler phrase ("Thanks for watching!", "Please subscribe", subtitle
credits) with *high* confidence, so the logprob gate in the pipeline lets it through. The
phrases are a small, well-known set, so match them directly.

Matching is against the WHOLE normalized segment text, never a substring, so a real
utterance that merely contains "thank you" is left alone -- only a segment that is nothing
but one of these artifacts is dropped. Subtitle-credit lines ("Subtitles by ...") are the
one exception: they are matched by prefix because their tail varies, and they are never
real speech in this app.
"""

from __future__ import annotations

import re

_STRIP_RE = re.compile(r"[^a-z0-9 ]+")
_SPACE_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    lowered = str(text).lower().strip()
    stripped = _STRIP_RE.sub("", lowered)  # drop punctuation, incl. apostrophes
    return _SPACE_RE.sub(" ", stripped).strip()


# Full-segment artifacts. Written naturally; normalized once at import so callers compare
# against the same canonical form ("don't" -> "dont", trailing "!" removed).
_PHRASES = frozenset(
    _normalize(p)
    for p in (
        "thanks for watching",
        "thanks for watching!",
        "thank you for watching",
        "thank you for watching.",
        "thanks for watching this video",
        "thank you for watching this video",
        "thanks for watching and see you next time",
        "please subscribe",
        "please subscribe to my channel",
        "like and subscribe",
        "don't forget to subscribe",
        "see you next time",
        "see you in the next video",
        "i'll see you in the next video",
    )
)

# Prefix-matched because the tail varies (community name, translator credit).
_PREFIXES = tuple(
    _normalize(p)
    for p in (
        "subtitles by",
        "subtitles created by",
        "subtitles amara org",
        "amara org",
    )
)


def is_hallucination(text: str) -> bool:
    """True if the segment text is nothing but a known near-silence filler phrase."""
    norm = _normalize(text)
    if not norm:
        return False
    if norm in _PHRASES:
        return True
    return any(norm.startswith(prefix) for prefix in _PREFIXES)
