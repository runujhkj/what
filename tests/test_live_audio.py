from what.audio import InputConfig
from what.live_audio import build_live_ffmpeg_sections, describe_live_capture_graph


def _cfg(**kwargs):
    base = dict(
        mode="desktop",
        mic_backend="avfoundation",
        mic_device=":1",
        file_path="",
        stdin_raw=False,
        mic_enabled=True,
        desktop_backend="avfoundation",
        desktop_device=":3",
        desktop_enabled=True,
    )
    base.update(kwargs)
    return InputConfig(**base)


def test_build_live_ffmpeg_sections_mixed_uses_mic_priority_ducking():
    sections, post = build_live_ffmpeg_sections(_cfg())
    assert sections[:4] == ["-f", "avfoundation", "-i", ":1"]
    filter_graph = " ".join(post)
    assert "sidechaincompress" in filter_graph
    assert "amix=inputs=2" in filter_graph
    assert "weights='1.0 0.45'" in filter_graph


def test_describe_live_capture_graph_mixed():
    inputs, mixed, mode = describe_live_capture_graph(_cfg())
    assert inputs == 2
    assert mixed is True
    assert mode == "desktop"
