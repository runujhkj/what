from dataclasses import dataclass


@dataclass(frozen=True)
class DesktopProbeSnapshot:
    probe_state: str
    code: int | None = None
    byte_count: int | None = None
    selector_label: str = ""


@dataclass(frozen=True)
class DesktopDecision:
    action: str
    reason: str


def classify_probe(snapshot: DesktopProbeSnapshot) -> DesktopDecision:
    state = (snapshot.probe_state or "").strip().lower()
    if state in {"active", "signal"}:
        return DesktopDecision(action="keep", reason="signal")
    if state in {"silent", ""}:
        # Policy: silence/no-data are not hard failures.
        return DesktopDecision(action="keep", reason="silent_or_no_probe")
    if state == "error":
        return DesktopDecision(action="fallback", reason="probe_error")
    # Unknown states should not trigger rebind churn.
    return DesktopDecision(action="keep", reason="unknown_state")


def should_retry_single_candidate(snapshot: DesktopProbeSnapshot) -> bool:
    decision = classify_probe(snapshot)
    return decision.action == "fallback"


def should_switch_candidate(snapshot: DesktopProbeSnapshot, switches: int, max_switches: int) -> bool:
    if switches >= max_switches:
        return False
    decision = classify_probe(snapshot)
    return decision.action == "fallback"
