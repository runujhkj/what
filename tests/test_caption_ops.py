from what.caption_ops import CaptionOpsBuilder


def _seg(seg_id: str, text: str, start_s: float, end_s: float) -> dict:
    return {
        "id": seg_id,
        "text": text,
        "abs_start": start_s,
        "abs_end": end_s,
    }


def test_gap_break_priority_over_width_break():
    builder = CaptionOpsBuilder(gap_break_ms=3000, max_visible_lines=3, max_chars_per_line=6)
    builder.build([_seg("s1", "hello", 0.0, 1.0)], ts_ms=1000)
    payload = builder.build([_seg("s2", "abcdef gh", 5.0, 6.0)], ts_ms=6000)

    assert payload is not None
    ops = payload["ops"]
    open_reasons = [op["reason"] for op in ops if op.get("op") == "line_open"]
    assert "gap" in open_reasons
    assert "width" in open_reasons
    assert open_reasons.index("gap") < open_reasons.index("width")


def test_line_evict_when_max_lines_exceeded():
    builder = CaptionOpsBuilder(gap_break_ms=1, max_visible_lines=2, max_chars_per_line=20)
    builder.build([_seg("s1", "one", 0.0, 0.1)], ts_ms=100)
    builder.build([_seg("s2", "two", 1.0, 1.1)], ts_ms=1100)
    payload = builder.build([_seg("s3", "three", 2.0, 2.1)], ts_ms=2100)

    assert payload is not None
    evicts = [op for op in payload["ops"] if op.get("op") == "line_evict"]
    assert len(evicts) == 1
    assert evicts[0]["reason"] == "max_lines"


def test_line_overflow_warning_for_long_single_token():
    builder = CaptionOpsBuilder(gap_break_ms=3000, max_visible_lines=2, max_chars_per_line=4)
    payload = builder.build([_seg("s1", "superlongword", 0.0, 0.2)], ts_ms=200)

    assert payload is not None
    warnings = [op for op in payload["ops"] if op.get("op") == "warning"]
    assert warnings
    assert warnings[0]["code"] == "line_overflow"
    appends = [op for op in payload["ops"] if op.get("op") == "line_append"]
    assert appends
    assert appends[0]["overflow_allowed"] is True

