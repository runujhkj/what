import copy
import os
from typing import Any, Dict

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib

DEFAULT_CONFIG_PATH = os.path.join("config", "default.toml")


def load_config(path: str | None = None) -> Dict[str, Any]:
    config_path = path or DEFAULT_CONFIG_PATH
    with open(config_path, "rb") as f:
        data = tomllib.load(f)
    return data


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def apply_preset(config: Dict[str, Any], preset_name: str | None) -> Dict[str, Any]:
    if not preset_name:
        return config
    presets = config.get("presets", {})
    preset = presets.get(preset_name)
    if not preset:
        raise ValueError(f"Unknown preset: {preset_name}")
    return deep_merge(config, preset)


def apply_profile(config: Dict[str, Any], profile_name: str | None) -> Dict[str, Any]:
    if not profile_name:
        return config
    profiles = config.get("profiles", {})
    profile = profiles.get(profile_name)
    if not profile:
        raise ValueError(f"Unknown profile: {profile_name}")
    return deep_merge(config, profile)
