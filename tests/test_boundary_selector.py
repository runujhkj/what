from array import array

from what.audio import AudioConfig, chunk_stream
from what.boundary_selector import select_cut_samples


def _pcm_from_samples(samples):
    buf = array("h", samples)
    return buf.tobytes()


def test_select_cut_samples_prefers_low_energy_candidate():
    sample_rate = 1000
    chunk_samples = 1000
    # Mostly loud, with a low-energy pocket near ~775 samples.
    samples = [12000] * chunk_samples
    for i in range(740, 810):
        samples[i] = 0
    cut, scores = select_cut_samples(
        _pcm_from_samples(samples),
        sample_rate=sample_rate,
        chunk_samples=chunk_samples,
        candidate_points=3,
        min_chunk_ratio=0.55,
        energy_window_ms=25,
    )
    assert len(scores) >= 3
    assert cut < chunk_samples
    assert any(point == cut for point, _ in scores)


def test_select_cut_samples_with_single_candidate_uses_full_chunk():
    sample_rate = 1000
    chunk_samples = 1000
    cut, scores = select_cut_samples(
        _pcm_from_samples([1000] * chunk_samples),
        sample_rate=sample_rate,
        chunk_samples=chunk_samples,
        candidate_points=1,
    )
    assert cut == chunk_samples
    assert scores == [(chunk_samples, 0.0)]


def test_chunk_stream_uses_boundary_selector_for_all_inputs():
    audio_cfg = AudioConfig(
        sample_rate=1000,
        channels=1,
        frame_ms=1000,
        chunk_ms=1000,
        overlap_ms=0,
        boundary_candidate_points=3,
    )
    # 2 chunk windows of audio with a low-energy pocket in each window.
    window = [12000] * 1000
    for i in range(740, 810):
        window[i] = 0
    frame = _pcm_from_samples(window + window)
    chunks = list(chunk_stream([frame], audio_cfg))
    assert len(chunks) >= 2
    assert all(int(c.cut_samples or 0) > 0 for c in chunks[:2])
    # Candidate selection should trim at least one chunk before full window.
    assert any(int(c.cut_samples or 0) < 1000 for c in chunks[:2])

