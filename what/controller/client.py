import json
import urllib.request
from typing import Any


def get_status(base_url: str) -> dict[str, Any]:
    return _get_json(f"{base_url}/control/status")


def get_gpu(base_url: str) -> dict[str, Any]:
    return _get_json(f"{base_url}/control/gpu")


def start(base_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    return _post_json(f"{base_url}/control/start", payload)


def stop(base_url: str) -> dict[str, Any]:
    return _post_json(f"{base_url}/control/stop", {})


def stream_start(base_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    return _post_json(f"{base_url}/control/stream/start", payload)


def stream_stop(base_url: str) -> dict[str, Any]:
    return _post_json(f"{base_url}/control/stream/stop", {})


def apply(base_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    return _post_json(f"{base_url}/control/apply", payload)


def set_publish_delay(base_url: str, publish_delay_seconds: int) -> dict[str, Any]:
    return _post_json(
        f"{base_url}/control/publish-delay",
        {"publish_delay_seconds": int(publish_delay_seconds)},
    )


def desktop_audio_status(base_url: str) -> dict[str, Any]:
    return _get_json(f"{base_url}/control/desktop-audio/status")


def desktop_audio_install(
    base_url: str,
    *,
    mode: str | None = None,
    configure_routing: bool | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if mode is not None:
        payload["mode"] = mode
    if configure_routing is not None:
        payload["configure_routing"] = bool(configure_routing)
    return _post_json(f"{base_url}/control/desktop-audio/install", payload)


def desktop_audio_uninstall(base_url: str) -> dict[str, Any]:
    return _post_json(f"{base_url}/control/desktop-audio/uninstall", {})


def _get_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))
