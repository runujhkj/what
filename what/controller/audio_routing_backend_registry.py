from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from .audio_routing_backends import (
    ensure_coreaudio,
    ensure_switch,
    remove_coreaudio,
    remove_switch,
)
from .audio_routing_contracts import unsupported_platform_status


class RoutingBackendAdapter(Protocol):
    key: str

    def probe(self, *, state_dir: Path, receipt: dict) -> dict:
        ...

    def ensure(self, *, state_dir: Path, state: dict) -> dict:
        ...

    def remove(self, *, state_dir: Path, state: dict) -> dict:
        ...


@dataclass(frozen=True)
class AdapterContext:
    expected_target_name: str
    fallback_target_pattern: str
    # Probing callbacks supplied by manager to preserve existing behavior.
    coreaudio_probe: Callable[[Path, dict], dict]
    switch_probe: Callable[[Path, dict], dict]
    # CoreAudio helpers.
    coreaudio_helper_path: Callable[[], str]
    coreaudio_prewarm_helper: Callable[[str, Path], dict]
    run_coreaudio_helper: Callable[..., dict]
    coreaudio_action_timeout_s: Callable[..., float]
    coreaudio_retry_on_timeout: Callable[[], bool]
    coreaudio_retry_timeout_s: Callable[[], float]
    # SwitchAudioSource helpers.
    run_switch: Callable[[str, list[str]], object]
    read_json: Callable[[Path], dict | None]
    write_json: Callable[[Path, dict], None]
    routing_receipt_path: Callable[[Path], Path]
    probe_routing: Callable[..., dict]


class MacCoreAudioAdapter:
    key = "coreaudio_aggregate"

    def __init__(self, ctx: AdapterContext) -> None:
        self._ctx = ctx

    def probe(self, *, state_dir: Path, receipt: dict) -> dict:
        return self._ctx.coreaudio_probe(state_dir, receipt)

    def ensure(self, *, state_dir: Path, state: dict) -> dict:
        return ensure_coreaudio(
            state_dir=state_dir,
            state=state,
            coreaudio_helper_path=self._ctx.coreaudio_helper_path,
            coreaudio_prewarm_helper=self._ctx.coreaudio_prewarm_helper,
            run_coreaudio_helper=self._ctx.run_coreaudio_helper,
            coreaudio_action_timeout_s=self._ctx.coreaudio_action_timeout_s,
            coreaudio_retry_on_timeout=self._ctx.coreaudio_retry_on_timeout,
            coreaudio_retry_timeout_s=self._ctx.coreaudio_retry_timeout_s,
        )

    def remove(self, *, state_dir: Path, state: dict) -> dict:
        return remove_coreaudio(
            state_dir=state_dir,
            state=state,
            coreaudio_helper_path=self._ctx.coreaudio_helper_path,
            run_coreaudio_helper=self._ctx.run_coreaudio_helper,
            coreaudio_action_timeout_s=self._ctx.coreaudio_action_timeout_s,
        )


class MacSwitchAudioSourceAdapter:
    key = "switchaudiosource"

    def __init__(self, ctx: AdapterContext) -> None:
        self._ctx = ctx

    def probe(self, *, state_dir: Path, receipt: dict) -> dict:
        return self._ctx.switch_probe(state_dir, receipt)

    def ensure(self, *, state_dir: Path, state: dict) -> dict:
        return ensure_switch(
            state_dir=state_dir,
            state=state,
            run_switch=self._ctx.run_switch,
            write_json=self._ctx.write_json,
            routing_receipt_path=self._ctx.routing_receipt_path,
            probe_routing=self._ctx.probe_routing,
        )

    def remove(self, *, state_dir: Path, state: dict) -> dict:
        return remove_switch(
            state_dir=state_dir,
            state=state,
            read_json=self._ctx.read_json,
            run_switch=self._ctx.run_switch,
            routing_receipt_path=self._ctx.routing_receipt_path,
            probe_routing=self._ctx.probe_routing,
        )


class StubBackendAdapter:
    def __init__(self, key: str, note: str) -> None:
        self.key = key
        self._note = note

    def probe(self, *, state_dir: Path, receipt: dict) -> dict:
        _ = (state_dir, receipt)
        status = unsupported_platform_status(
            enabled=True,
            backend=self.key,
            expected_name="what-desktop",
        )
        status["note"] = self._note
        status["manual_steps"] = [self._note]
        return status

    def ensure(self, *, state_dir: Path, state: dict) -> dict:
        _ = state
        return {"ok": False, "error": "unsupported_platform", "routing": self.probe(state_dir=state_dir, receipt={})}

    def remove(self, *, state_dir: Path, state: dict) -> dict:
        _ = state
        return {"ok": False, "error": "unsupported_platform", "routing": self.probe(state_dir=state_dir, receipt={})}


def resolve_backend_adapter(
    *,
    platform: str,
    backend_name: str,
    ctx: AdapterContext,
) -> RoutingBackendAdapter:
    # macOS implementations (active)
    if platform == "darwin":
        if backend_name == "coreaudio_aggregate":
            return MacCoreAudioAdapter(ctx)
        if backend_name == "switchaudiosource":
            return MacSwitchAudioSourceAdapter(ctx)
        # Unknown backend on mac: explicit stub.
        return StubBackendAdapter(
            backend_name,
            f"backend '{backend_name}' is not implemented on macOS",
        )

    # Windows/Linux placeholders for the planned native routing implementations.
    if platform.startswith("win"):
        return StubBackendAdapter(
            "windows_wasapi",
            "Windows WASAPI routing backend not implemented yet.",
        )
    if platform.startswith("linux"):
        return StubBackendAdapter(
            "linux_pipewire_pulse",
            "Linux PipeWire/Pulse routing backend not implemented yet.",
        )
    return StubBackendAdapter(
        backend_name,
        f"platform '{platform}' has no routing backend implementation yet.",
    )
