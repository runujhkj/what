from dataclasses import dataclass, field
from typing import Any


@dataclass
class _Line:
    line_id: str
    text: str = ""
    open: bool = True
    last_segment_end_ms: int = 0


@dataclass
class CaptionOpsBuilder:
    session_id: str = "default"
    gap_break_ms: int = 3000
    max_visible_lines: int = 3
    max_chars_per_line: int = 56
    punct_commit_enabled: bool = True
    punct_min_fill_ratio: float = 0.55
    fill_commit_enabled: bool = True
    fill_commit_ratio: float = 0.55
    _seq: int = 0
    _line_index: int = 0
    _lines: list[_Line] = field(default_factory=list)

    def build(self, seg_list: list[dict[str, Any]], ts_ms: int) -> dict[str, Any] | None:
        ops: list[dict[str, Any]] = []
        for seg in seg_list:
            text = " ".join((seg.get("text") or "").split())
            if not text:
                continue
            start_ms = int(float(seg.get("abs_start", 0.0)) * 1000.0)
            end_ms = int(float(seg.get("abs_end", 0.0)) * 1000.0)
            seg_id = str(seg.get("id", ""))
            self._append_segment(text, seg_id, start_ms, end_ms, ops)
        if not ops:
            return None
        self._seq += 1
        return {
            "type": "caption_ops",
            "session_id": self.session_id,
            "seq": self._seq,
            "ts_ms": int(ts_ms),
            "ops": ops,
        }

    def _append_segment(
        self, text: str, segment_id: str, start_ms: int, end_ms: int, ops: list[dict[str, Any]]
    ) -> None:
        if not self._lines:
            self._open_line("manual", segment_id, start_ms, end_ms, ops)
        else:
            cur = self._lines[-1]
            gap = max(0, start_ms - cur.last_segment_end_ms)
            if not cur.open:
                self._open_line(
                    "gap" if gap >= self.gap_break_ms else "manual",
                    segment_id,
                    start_ms,
                    end_ms,
                    ops,
                )
                cur = self._lines[-1]
            if gap >= self.gap_break_ms:
                self._close_line(cur, ops)
                self._open_line("gap", segment_id, start_ms, end_ms, ops)

        cur = self._lines[-1]
        words = text.split()
        appended: list[str] = []
        for word in words:
            candidate = word if not cur.text else f"{cur.text} {word}"
            if len(candidate) <= self.max_chars_per_line:
                cur.text = candidate
                cur.last_segment_end_ms = end_ms
                appended.append(word)
                continue

            if appended:
                self._append_words(cur, appended, segment_id, ops)
                appended = []
            self._close_line(cur, ops)
            self._open_line("width", segment_id, start_ms, end_ms, ops)
            cur = self._lines[-1]
            cur.text = word
            cur.last_segment_end_ms = end_ms
            appended.append(word)
            if len(word) > self.max_chars_per_line:
                self._emit_overflow_warning(cur.line_id, segment_id, len(word), ops)

        if appended:
            self._append_words(cur, appended, segment_id, ops)

        self._maybe_commit_on_punctuation(cur, segment_id, start_ms, end_ms, ops)
        self._maybe_commit_on_fill(cur, segment_id, start_ms, end_ms, ops)

    def _append_words(
        self, line: _Line, words: list[str], segment_id: str, ops: list[dict[str, Any]]
    ) -> None:
        if not words:
            return
        ops.append(
            {
                "op": "line_append",
                "line_id": line.line_id,
                "text": " ".join(words),
                "segment_id": segment_id,
                "overflow_allowed": True,
            }
        )

    def _close_line(self, line: _Line, ops: list[dict[str, Any]]) -> None:
        if not line.open:
            return
        line.open = False
        ops.append({"op": "line_close", "line_id": line.line_id})

    def _maybe_commit_on_punctuation(
        self,
        line: _Line,
        segment_id: str,
        start_ms: int,
        end_ms: int,
        ops: list[dict[str, Any]],
    ) -> None:
        if not self.punct_commit_enabled or not line.open:
            return
        text = (line.text or "").rstrip()
        if not text:
            return
        if text[-1] not in ".?!":
            return
        max_chars = max(1, self.max_chars_per_line)
        fill_ratio = len(text) / float(max_chars)
        if fill_ratio < max(0.0, min(1.0, self.punct_min_fill_ratio)):
            return
        self._close_line(line, ops)

    def _maybe_commit_on_fill(
        self,
        line: _Line,
        segment_id: str,
        start_ms: int,
        end_ms: int,
        ops: list[dict[str, Any]],
    ) -> None:
        if not self.fill_commit_enabled or not line.open:
            return
        text = (line.text or "").rstrip()
        if not text:
            return
        max_chars = max(1, self.max_chars_per_line)
        fill_ratio = len(text) / float(max_chars)
        if fill_ratio < max(0.0, min(1.0, self.fill_commit_ratio)):
            return
        self._close_line(line, ops)

    def _open_line(
        self,
        reason: str,
        segment_id: str,
        start_ms: int,
        end_ms: int,
        ops: list[dict[str, Any]],
    ) -> None:
        self._line_index += 1
        line_id = f"l_{self._line_index:06d}"
        if len(self._lines) >= self.max_visible_lines:
            evicted = self._lines.pop(0)
            ops.append({"op": "line_evict", "line_id": evicted.line_id, "reason": "max_lines"})
        self._lines.append(
            _Line(line_id=line_id, text="", open=True, last_segment_end_ms=end_ms)
        )
        after_line_id = self._lines[-2].line_id if len(self._lines) > 1 else ""
        ops.append(
            {
                "op": "line_open",
                "line_id": line_id,
                "after_line_id": after_line_id,
                "reason": reason,
                "segment_id": segment_id,
                "segment_start_ms": start_ms,
                "segment_end_ms": end_ms,
            }
        )

    def _emit_overflow_warning(
        self, line_id: str, segment_id: str, word_len: int, ops: list[dict[str, Any]]
    ) -> None:
        ops.append(
            {
                "op": "warning",
                "line_id": line_id,
                "segment_id": segment_id,
                "code": "line_overflow",
                "message": f"word length {word_len} exceeds max_chars_per_line",
            }
        )
