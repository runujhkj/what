from __future__ import annotations

from array import array


def _to_int16_samples(pcm_bytes: bytes) -> array:
    samples = array("h")
    samples.frombytes(pcm_bytes)
    return samples


def _candidate_points(min_cut_samples: int, max_cut_samples: int, count: int) -> list[int]:
    if count <= 1 or min_cut_samples >= max_cut_samples:
        return [max_cut_samples]
    span = max_cut_samples - min_cut_samples
    out: list[int] = []
    for i in range(count):
        pos = min_cut_samples + int(round((span * i) / (count - 1)))
        if pos not in out:
            out.append(pos)
    if out[-1] != max_cut_samples:
        out.append(max_cut_samples)
    return out


def select_cut_samples(
    pcm_bytes: bytes,
    *,
    sample_rate: int,
    chunk_samples: int,
    candidate_points: int = 3,
    min_chunk_ratio: float = 0.55,
    energy_window_ms: int = 25,
) -> tuple[int, list[tuple[int, float]]]:
    points = max(1, int(candidate_points or 1))
    if points <= 1:
        return chunk_samples, [(chunk_samples, 0.0)]

    min_cut_samples = max(1, int(chunk_samples * max(0.1, min(0.95, min_chunk_ratio))))
    max_cut_samples = max(1, chunk_samples)
    candidates = _candidate_points(min_cut_samples, max_cut_samples, points)
    if not pcm_bytes:
        return max_cut_samples, [(p, 0.0) for p in candidates]

    samples = _to_int16_samples(pcm_bytes)
    if not samples:
        return max_cut_samples, [(p, 0.0) for p in candidates]

    radius = max(1, int(sample_rate * max(5, energy_window_ms) / 1000))
    scored: list[tuple[int, float]] = []
    for cut in candidates:
        end = min(len(samples), max(1, cut))
        start = max(0, end - radius)
        if end <= start:
            score = 0.0
        else:
            window = samples[start:end]
            score = float(sum(abs(int(x)) for x in window)) / float(len(window))
        scored.append((cut, score))

    scored.sort(key=lambda x: (x[1], x[0]))
    chosen = int(scored[0][0]) if scored else max_cut_samples
    scored.sort(key=lambda x: x[0])
    return chosen, scored

