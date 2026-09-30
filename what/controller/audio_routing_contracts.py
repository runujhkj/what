from __future__ import annotations


def unsupported_platform_status(*, enabled: bool, backend: str, expected_name: str) -> dict:
    return {
        "supported": False,
        "enabled": enabled,
        "ready": False,
        "changed": False,
        "name_expected": expected_name,
        "note": "Routing manager is macOS-only.",
        "manual_steps": [],
        "manager": "",
        "current_output": "",
        "target_output": "",
        "can_route": False,
        "can_restore": False,
        "backend": backend,
        "blockers": ["unsupported_platform"],
    }


def routing_disabled_status(*, backend: str, expected_name: str) -> dict:
    return {
        "supported": True,
        "enabled": False,
        "ready": False,
        "changed": False,
        "name_expected": expected_name,
        "note": "Routing manager is disabled (set WHAT_DESKTOP_ROUTING_ENABLE=1 to enable).",
        "manual_steps": [],
        "manager": "",
        "current_output": "",
        "target_output": "",
        "can_route": False,
        "can_restore": False,
        "backend": backend,
        "blockers": ["routing_disabled"],
    }


def coreaudio_missing_helper_status(
    *,
    expected_name: str,
    helper_path: str,
    can_restore: bool,
) -> dict:
    return {
        "supported": True,
        "enabled": True,
        "ready": False,
        "changed": False,
        "name_expected": expected_name,
        "note": "CoreAudio aggregate backend selected but helper is missing.",
        "manual_steps": [
            "CoreAudio aggregate backend helper is not available yet. "
            "Set WHAT_DESKTOP_ROUTING_BACKEND=switchaudiosource for current automation."
        ],
        "manager": "coreaudio_aggregate",
        "manager_path": helper_path,
        "current_output": "",
        "target_output": expected_name,
        "target_is_expected": False,
        "can_route": False,
        "can_restore": can_restore,
        "backend": "coreaudio_aggregate",
        "blockers": ["missing_coreaudio_helper"],
    }


def coreaudio_probe_timeout_status(*, helper_path: str, can_restore: bool) -> dict:
    return {
        "supported": True,
        "enabled": True,
        "ready": False,
        "changed": False,
        "name_expected": "what-desktop",
        "note": "CoreAudio probe timed out; helper may be compiling or blocked.",
        "manual_steps": [
            "Retry in a moment.",
            "If this persists, run desktop install/uninstall once to collect helper error details.",
        ],
        "manager": "coreaudio_aggregate",
        "manager_path": helper_path,
        "current_output": "",
        "target_output": "",
        "target_is_expected": False,
        "can_route": True,
        "can_restore": can_restore,
        "backend": "coreaudio_aggregate",
        "blockers": ["coreaudio_probe_timeout"],
    }


def switch_missing_manager_status(*, expected_name: str, can_restore: bool) -> dict:
    return {
        "supported": True,
        "enabled": True,
        "ready": False,
        "changed": False,
        "name_expected": expected_name,
        "note": "SwitchAudioSource helper not found; routing automation unavailable.",
        "manual_steps": [
            "Install switchaudio-osx (SwitchAudioSource) and rerun setup.",
            "Manually set output to 'what-desktop' (preferred) or BlackHole as fallback.",
        ],
        "manager": "",
        "current_output": "",
        "target_output": "",
        "can_route": False,
        "can_restore": can_restore,
        "backend": "switchaudiosource",
        "blockers": ["missing_switchaudiosource"],
    }

