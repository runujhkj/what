from what.config import load_config


def test_cpu_friendly_profile_exists():
    cfg = load_config()
    profiles = cfg.get("profiles", {})
    assert "cpu_friendly" in profiles
    cpu = profiles["cpu_friendly"]
    assert "audio" in cpu
    assert "asr" in cpu
    assert "output" in cpu
