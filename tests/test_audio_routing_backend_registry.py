from __future__ import annotations

from pathlib import Path

from what.controller.audio_routing_backend_registry import (
    AdapterContext,
    MacCoreAudioAdapter,
    MacSwitchAudioSourceAdapter,
    StubBackendAdapter,
    resolve_backend_adapter,
)


def _ctx() -> AdapterContext:
    return AdapterContext(
        expected_target_name="what-desktop",
        fallback_target_pattern="blackhole",
        coreaudio_probe=lambda _state_dir, _receipt: {"backend": "coreaudio_aggregate", "ok": True},
        switch_probe=lambda _state_dir, _receipt: {"backend": "switchaudiosource", "ok": True},
        coreaudio_helper_path=lambda: "/tmp/what-coreaudio-routing",
        coreaudio_prewarm_helper=lambda _helper, _state_dir: {"ok": True},
        run_coreaudio_helper=lambda *_args, **_kwargs: {"ok": True, "routing": {"backend": "coreaudio_aggregate"}},
        coreaudio_action_timeout_s=lambda **_kwargs: 3.0,
        coreaudio_retry_on_timeout=lambda: False,
        coreaudio_retry_timeout_s=lambda: 3.0,
        run_switch=lambda _bin, _args: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
        read_json=lambda _path: None,
        write_json=lambda _path, _data: None,
        routing_receipt_path=lambda state_dir: Path(state_dir) / "r.json",
        probe_routing=lambda **_kwargs: {"ok": True},
    )


def test_resolve_backend_adapter_mac_coreaudio():
    adapter = resolve_backend_adapter(platform="darwin", backend_name="coreaudio_aggregate", ctx=_ctx())
    assert isinstance(adapter, MacCoreAudioAdapter)


def test_resolve_backend_adapter_mac_switch():
    adapter = resolve_backend_adapter(platform="darwin", backend_name="switchaudiosource", ctx=_ctx())
    assert isinstance(adapter, MacSwitchAudioSourceAdapter)


def test_resolve_backend_adapter_windows_stub():
    adapter = resolve_backend_adapter(platform="win32", backend_name="coreaudio_aggregate", ctx=_ctx())
    assert isinstance(adapter, StubBackendAdapter)
    status = adapter.probe(state_dir=Path("."), receipt={})
    assert status.get("backend") == "windows_wasapi"
    assert status.get("supported") is False


def test_resolve_backend_adapter_linux_stub():
    adapter = resolve_backend_adapter(platform="linux", backend_name="coreaudio_aggregate", ctx=_ctx())
    assert isinstance(adapter, StubBackendAdapter)
    status = adapter.probe(state_dir=Path("."), receipt={})
    assert status.get("backend") == "linux_pipewire_pulse"
    assert status.get("supported") is False
