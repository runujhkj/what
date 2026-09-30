from what.client.dead_input import DeadInputDetector

ZEROS = b"\x00" * 4096
NOISE = b"\x03\x00\xfd\xff" * 1024  # quiet room: tiny but nonzero samples


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_sustained_zeros_warn_once_then_recover():
    clock = Clock()
    detector = DeadInputDetector("VB-Cable", threshold_sec=3.0, clock=clock)
    assert detector.observe(ZEROS) is None
    clock.now = 2.9
    assert detector.observe(ZEROS) is None
    clock.now = 3.0
    warning = detector.observe(ZEROS)
    assert warning.startswith("capture warning:") and "VB-Cable" in warning
    clock.now = 10.0
    assert detector.observe(ZEROS) is None
    assert detector.observe(NOISE).startswith("capture recovered:")
    assert detector.observe(NOISE) is None


def test_quiet_but_live_input_never_warns():
    clock = Clock()
    detector = DeadInputDetector(":default", clock=clock)
    for step in range(100):
        clock.now = step * 0.25
        assert detector.observe(NOISE) is None


def test_brief_digital_silence_resets():
    clock = Clock()
    detector = DeadInputDetector(":default", threshold_sec=3.0, clock=clock)
    detector.observe(ZEROS)
    clock.now = 2.0
    detector.observe(NOISE)
    clock.now = 4.0
    assert detector.observe(ZEROS) is None
