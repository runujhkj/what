from what.service.stats import StatsTracker


def test_stats_tracker_updates():
    tracker = StatsTracker(alpha=0.5)
    tracker.update(processing_sec=0.5, audio_sec=1.0)
    snap = tracker.snapshot()
    assert snap.samples == 1
    assert snap.avg_rtf == 0.5
    assert snap.avg_processing_ms == 500.0
    assert snap.avg_audio_ms == 1000.0
    assert snap.last_update > 0


def test_stats_tracker_ema():
    tracker = StatsTracker(alpha=0.5)
    tracker.update(processing_sec=1.0, audio_sec=1.0)  # rtf=1.0
    tracker.update(processing_sec=0.0, audio_sec=1.0)  # rtf=0.0
    snap = tracker.snapshot()
    assert snap.samples == 2
    assert 0.0 < snap.avg_rtf < 1.0
