"""The desktop helper must not splice invented silence into real audio.

ffmpeg's PulseAudio input delivers audio in bursts. The helper used to send a silent frame
every time one 30ms select() passed without data -- i.e. in every gap between bursts --
and then send the real audio for that gap when it arrived. On a real session that inserted
5,313 silent 30ms frames at a steady 90ms rhythm, made the recording 1.5x longer than the
time that passed, and put an 11 Hz chop into desktop replay and the OBS recording.

These tests model the select() loop against a bursty capture, with a fake clock, and pin
both halves of the contract: no fabricated frames in normal delivery, and real-time padding
when the capture genuinely stalls.
"""

import pytest

from what.native_desktop_helper import StreamClock

FRAME_S = 0.030


def simulate(duration_s, burst_period_s, frames_per_burst, rule, stall=None):
    """Drive a select()-with-timeout loop over a bursty source.

    rule: "old" (one silent frame per empty select) or "clock" (StreamClock).
    stall: (start_s, end_s) during which the capture delivers nothing at all.
    Returns (stream_seconds_per_wall_second, fabricated_frames_inserted_between_bursts,
             total_fill_frames).
    """
    t = 0.0
    clock = StreamClock(FRAME_S, 0.25, now=lambda: t)
    next_burst = burst_period_s
    real = fill = interleaved = 0
    since_last_burst_fill = 0
    while t < duration_s:
        stalled = stall is not None and stall[0] <= next_burst < stall[1]
        if stalled:
            next_burst = stall[1]
        if next_burst <= t + FRAME_S:
            t = max(t, next_burst)
            next_burst += burst_period_s
            real += frames_per_burst
            clock.note_sent(frames_per_burst)
            # silence sent between two deliveries of real audio = spliced into the stream
            interleaved += since_last_burst_fill
            since_last_burst_fill = 0
        else:
            t += FRAME_S
            n = 1 if rule == "old" else clock.fill_frames()
            clock.note_sent(n)
            fill += n
            since_last_burst_fill += n
    return (real + fill) * FRAME_S / duration_s, interleaved, fill


def test_old_rule_reproduces_the_chop():
    """Documents the bug: bursty delivery made the stream run far faster than real time,
    with silence spliced between every burst."""
    rate, interleaved, _ = simulate(60, 0.09, 3, rule="old")
    assert rate > 1.3
    assert interleaved > 1000


def test_bursty_delivery_inserts_no_silence():
    rate, interleaved, fill = simulate(60, 0.09, 3, rule="clock")
    assert interleaved == 0, "silence was spliced between bursts of real audio"
    assert fill == 0
    assert rate == pytest.approx(1.0, abs=0.01)


@pytest.mark.parametrize("period,frames", [(0.06, 2), (0.12, 4), (0.20, 7)])
def test_other_burst_sizes_are_also_clean(period, frames):
    """ffmpeg's burst size depends on the backend's fragment size; don't overfit to 90ms.
    Anything below the stall threshold must pass untouched."""
    _, interleaved, _ = simulate(30, period, frames, rule="clock")
    assert interleaved == 0


def test_a_genuine_stall_is_padded_to_real_time():
    """A suspended sink delivers nothing; the ASR stream still needs its clock to move."""
    rate, _, fill = simulate(20, 0.09, 3, rule="clock", stall=(5.0, 8.0))
    assert fill * FRAME_S == pytest.approx(3.0, abs=0.3)
    assert rate == pytest.approx(1.0, abs=0.03)


def test_no_padding_below_the_stall_threshold():
    t = [0.0]
    clock = StreamClock(FRAME_S, 0.25, now=lambda: t[0])
    t[0] = 0.24
    assert clock.fill_frames() == 0


def test_padding_catches_up_without_overshooting():
    t = [0.0]
    clock = StreamClock(FRAME_S, 0.25, now=lambda: t[0])
    t[0] = 1.0
    n = clock.fill_frames()
    clock.note_sent(n)
    assert 0 <= clock.behind_s() < FRAME_S
    assert clock.fill_frames() == 0


def test_stall_threshold_is_never_below_one_frame():
    clock = StreamClock(FRAME_S, 0.0)
    assert clock.stall_s == FRAME_S


def test_helper_stream_loop_uses_the_clock():
    """Guard the wiring: the empty-select branch must defer to the clock, not send a frame
    unconditionally."""
    import inspect

    from what import native_desktop_helper as helper

    src = inspect.getsource(helper._stream_loop)
    timeout_branch = src.split("if not ready:", 1)[1].split("continue", 1)[0]
    assert "clock.fill_frames()" in timeout_branch
    sends = timeout_branch.count("await ws.send(silence_frame)")
    loops = timeout_branch.count("for _ in range(clock.fill_frames())")
    assert sends == loops == 1, "a silence send in the timeout branch isn't gated by the clock"
