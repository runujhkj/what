from ..config import apply_preset, apply_profile, load_config


def load_cfg(config_path: str | None, preset_name: str | None, profile_name: str | None) -> dict:
    cfg = load_config(config_path)
    cfg = apply_preset(cfg, preset_name)
    cfg = apply_profile(cfg, profile_name)
    return cfg


def validate_language(lang: str | None, cfg: dict) -> None:
    allowed_langs = cfg.get("languages", {}).get("allowed", [])
    if lang == "auto":
        raise NotImplementedError("auto language detection is stubbed for now")
    if lang and lang not in allowed_langs:
        raise ValueError(f"Unsupported language: {lang}")
