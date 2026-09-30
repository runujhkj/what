from what.controller.desktop_capture_state_machine import (
    DesktopProbeSnapshot,
    classify_probe,
    should_retry_single_candidate,
    should_switch_candidate,
)


def test_classify_probe_keeps_on_silent() -> None:
    decision = classify_probe(DesktopProbeSnapshot(probe_state="silent"))
    assert decision.action == "keep"
    assert decision.reason == "silent_or_no_probe"


def test_classify_probe_fallbacks_on_error() -> None:
    decision = classify_probe(DesktopProbeSnapshot(probe_state="error"))
    assert decision.action == "fallback"
    assert decision.reason == "probe_error"


def test_switch_only_on_hard_error_and_budget() -> None:
    snap_silent = DesktopProbeSnapshot(probe_state="silent", code=0, byte_count=1000)
    assert should_switch_candidate(snap_silent, switches=0, max_switches=2) is False

    snap_error = DesktopProbeSnapshot(probe_state="error")
    assert should_switch_candidate(snap_error, switches=0, max_switches=2) is True
    assert should_switch_candidate(snap_error, switches=2, max_switches=2) is False


def test_single_candidate_retry_only_on_error() -> None:
    assert should_retry_single_candidate(DesktopProbeSnapshot(probe_state="silent")) is False
    assert should_retry_single_candidate(DesktopProbeSnapshot(probe_state="error")) is True
