from what.controller.routes_stream import _should_rebuild_for_true_zero


def test_should_rebuild_for_true_zero_when_all_candidates_are_silent_zero_with_bytes():
    assert _should_rebuild_for_true_zero(
        probe_state="silent",
        detail_code=0,
        detail_bytes=9834,
        scans=[(":3", "silent", 0), (":0", "silent", 0)],
    ) is True


def test_should_not_rebuild_without_bytes_or_with_signal_candidate():
    assert _should_rebuild_for_true_zero(
        probe_state="silent",
        detail_code=0,
        detail_bytes=0,
        scans=[(":3", "silent", 0), (":0", "silent", 0)],
    ) is False
    assert _should_rebuild_for_true_zero(
        probe_state="silent",
        detail_code=0,
        detail_bytes=1200,
        scans=[(":3", "signal", 4), (":0", "silent", 0)],
    ) is False
