import json
import subprocess
from pathlib import Path

from what.controller import audio_routing_manager as arm


def test_probe_disabled(monkeypatch, tmp_path):
    monkeypatch.setattr(arm, "_is_mac", lambda: True)
    monkeypatch.setenv("WHAT_DESKTOP_ROUTING_ENABLE", "0")
    monkeypatch.delenv("WHAT_DESKTOP_ROUTING_BACKEND", raising=False)
    status = arm.probe_routing(state_dir=tmp_path)
    assert status["enabled"] is False
    assert status["can_route"] is False
    assert status["backend"] == "coreaudio_aggregate"
    assert "routing_disabled" in status["blockers"]

def test_probe_defaults_to_coreaudio_enabled_on_mac(monkeypatch, tmp_path):
    monkeypatch.setattr(arm, "_is_mac", lambda: True)
    monkeypatch.delenv("WHAT_DESKTOP_ROUTING_ENABLE", raising=False)
    monkeypatch.delenv("WHAT_DESKTOP_ROUTING_BACKEND", raising=False)
    monkeypatch.setattr(arm, "_coreaudio_helper_path", lambda: "")
    status = arm.probe_routing(state_dir=tmp_path)
    assert status["enabled"] is True
    assert status["backend"] == "coreaudio_aggregate"


def test_probe_missing_switch(monkeypatch, tmp_path):
    monkeypatch.setattr(arm, "_is_mac", lambda: True)
    monkeypatch.setenv("WHAT_DESKTOP_ROUTING_ENABLE", "1")
    monkeypatch.setenv("WHAT_DESKTOP_ROUTING_BACKEND", "switchaudiosource")
    monkeypatch.setattr(arm, "_find_switch_audio_source", lambda: "")
    status = arm.probe_routing(state_dir=tmp_path)
    assert status["enabled"] is True
    assert status["can_route"] is False
    assert "SwitchAudioSource" in status["note"]
    assert status["backend"] == "switchaudiosource"
    assert "missing_switchaudiosource" in status["blockers"]


def test_probe_missing_target_output_contract(monkeypatch, tmp_path):
    monkeypatch.setattr(arm, "_is_mac", lambda: True)
    monkeypatch.setenv("WHAT_DESKTOP_ROUTING_ENABLE", "1")
    monkeypatch.setenv("WHAT_DESKTOP_ROUTING_BACKEND", "switchaudiosource")
    monkeypatch.setattr(arm, "_find_switch_audio_source", lambda: "/usr/local/bin/SwitchAudioSource")
    monkeypatch.setattr(arm, "_list_outputs", lambda _b: ["MacBook Pro Speakers", "Display Audio"])
    monkeypatch.setattr(arm, "_current_output", lambda _b: "MacBook Pro Speakers")

    status = arm.probe_routing(state_dir=tmp_path)
    assert status["backend"] == "switchaudiosource"
    assert status["ready"] is False
    assert status["target_output"] == ""
    assert "missing_target_output" in status["blockers"]
    assert len(status["manual_steps"]) >= 2
    assert "Create 'what-desktop'" in status["manual_steps"][0]


def test_probe_ready_on_expected_target(monkeypatch, tmp_path):
    monkeypatch.setattr(arm, "_is_mac", lambda: True)
    monkeypatch.setenv("WHAT_DESKTOP_ROUTING_ENABLE", "1")
    monkeypatch.setenv("WHAT_DESKTOP_ROUTING_BACKEND", "switchaudiosource")
    monkeypatch.setattr(arm, "_find_switch_audio_source", lambda: "/usr/local/bin/SwitchAudioSource")
    monkeypatch.setattr(arm, "_list_outputs", lambda _b: ["what-desktop", "BlackHole 2ch"])
    monkeypatch.setattr(arm, "_current_output", lambda _b: "what-desktop")
    status = arm.probe_routing(state_dir=tmp_path)
    assert status["ready"] is True
    assert status["target_output"] == "what-desktop"
    assert status["target_is_expected"] is True
    assert status["backend"] == "switchaudiosource"


def test_probe_ready_on_legacy_what_alias_target(monkeypatch, tmp_path):
    monkeypatch.setattr(arm, "_is_mac", lambda: True)
    monkeypatch.setenv("WHAT_DESKTOP_ROUTING_ENABLE", "1")
    monkeypatch.setenv("WHAT_DESKTOP_ROUTING_BACKEND", "switchaudiosource")
    monkeypatch.setattr(arm, "_find_switch_audio_source", lambda: "/usr/local/bin/SwitchAudioSource")
    monkeypatch.setattr(arm, "_list_outputs", lambda _b: ["what-d", "BlackHole 2ch"])
    monkeypatch.setattr(arm, "_current_output", lambda _b: "what-d")
    status = arm.probe_routing(state_dir=tmp_path)
    assert status["ready"] is True
    assert status["target_output"] == "what-d"
    assert status["target_is_expected"] is True
    assert "legacy what-*" in str(status.get("note", "")).lower()


def test_ensure_routing_switches_output_and_writes_receipt(monkeypatch, tmp_path):
    monkeypatch.setattr(arm, "_is_mac", lambda: True)
    monkeypatch.setenv("WHAT_DESKTOP_ROUTING_ENABLE", "1")
    monkeypatch.setenv("WHAT_DESKTOP_ROUTING_BACKEND", "switchaudiosource")
    monkeypatch.setattr(arm, "_find_switch_audio_source", lambda: "/usr/local/bin/SwitchAudioSource")

    state = {"output": "Built-in Output"}

    def fake_list(_b):
        return ["what-desktop", "BlackHole 2ch", "Built-in Output"]

    def fake_current(_b):
        return state["output"]

    def fake_run(_b, args):
        if args[:3] == ["-s", "what-desktop", "-t"]:
            state["output"] = "what-desktop"
        return subprocess.CompletedProcess(args=["SwitchAudioSource"], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(arm, "_list_outputs", fake_list)
    monkeypatch.setattr(arm, "_current_output", fake_current)
    monkeypatch.setattr(arm, "_run_switch", fake_run)

    result = arm.ensure_routing(Path("."), state_dir=tmp_path)
    assert result["ok"] is True
    assert result["changed"] is True
    receipt = tmp_path / arm.ROUTING_RECEIPT_FILE
    data = json.loads(receipt.read_text(encoding="utf-8"))
    assert data["previous_output"] == "Built-in Output"
    assert data["routed_output"] == "what-desktop"


def test_remove_managed_routing_restores_previous_output(monkeypatch, tmp_path):
    monkeypatch.setattr(arm, "_is_mac", lambda: True)
    monkeypatch.setenv("WHAT_DESKTOP_ROUTING_ENABLE", "1")
    monkeypatch.setenv("WHAT_DESKTOP_ROUTING_BACKEND", "switchaudiosource")
    monkeypatch.setattr(arm, "_find_switch_audio_source", lambda: "/usr/local/bin/SwitchAudioSource")

    receipt = tmp_path / arm.ROUTING_RECEIPT_FILE
    receipt.write_text(
        json.dumps({"version": 1, "previous_output": "Built-in Output"}),
        encoding="utf-8",
    )
    state = {"output": "what-desktop"}

    monkeypatch.setattr(arm, "_list_outputs", lambda _b: ["what-desktop", "Built-in Output"])
    monkeypatch.setattr(arm, "_current_output", lambda _b: state["output"])

    def fake_run(_b, args):
        if args[:3] == ["-s", "Built-in Output", "-t"]:
            state["output"] = "Built-in Output"
        return subprocess.CompletedProcess(args=["SwitchAudioSource"], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(arm, "_run_switch", fake_run)

    result = arm.remove_managed_routing(Path("."), state_dir=tmp_path)
    assert result["ok"] is True
    assert result["changed"] is True
    assert receipt.exists() is False


def test_remove_managed_routing_without_previous_output_clears_receipt(monkeypatch, tmp_path):
    monkeypatch.setattr(arm, "_is_mac", lambda: True)
    monkeypatch.setenv("WHAT_DESKTOP_ROUTING_ENABLE", "1")
    monkeypatch.setenv("WHAT_DESKTOP_ROUTING_BACKEND", "switchaudiosource")
    monkeypatch.setattr(arm, "_find_switch_audio_source", lambda: "/usr/local/bin/SwitchAudioSource")
    monkeypatch.setattr(arm, "_list_outputs", lambda _b: ["what-desktop", "Built-in Output"])
    monkeypatch.setattr(arm, "_current_output", lambda _b: "what-desktop")

    receipt = tmp_path / arm.ROUTING_RECEIPT_FILE
    receipt.write_text(json.dumps({"version": 1}), encoding="utf-8")

    result = arm.remove_managed_routing(Path("."), state_dir=tmp_path)
    assert result["ok"] is True
    assert result["changed"] is False
    assert receipt.exists() is False


def test_ensure_routing_switch_failure_passes_through_error_fields(monkeypatch, tmp_path):
    monkeypatch.setattr(arm, "_is_mac", lambda: True)
    monkeypatch.setenv("WHAT_DESKTOP_ROUTING_ENABLE", "1")
    monkeypatch.setenv("WHAT_DESKTOP_ROUTING_BACKEND", "switchaudiosource")
    monkeypatch.setattr(arm, "_find_switch_audio_source", lambda: "/usr/local/bin/SwitchAudioSource")
    monkeypatch.setattr(arm, "_list_outputs", lambda _b: ["what-desktop", "Built-in Output"])
    monkeypatch.setattr(arm, "_current_output", lambda _b: "Built-in Output")
    monkeypatch.setattr(
        arm,
        "_run_switch",
        lambda _b, _args: subprocess.CompletedProcess(
            args=["SwitchAudioSource"],
            returncode=42,
            stdout="stdout-line",
            stderr="stderr-line",
        ),
    )

    result = arm.ensure_routing(Path("."), state_dir=tmp_path)
    assert result["ok"] is False
    assert result["error"] == "route_failed"
    assert result["code"] == 42
    assert "stdout-line" in result["stdout"]
    assert "stderr-line" in result["stderr"]


def test_coreaudio_backend_reports_missing_helper(monkeypatch, tmp_path):
    monkeypatch.setattr(arm, "_is_mac", lambda: True)
    monkeypatch.setenv("WHAT_DESKTOP_ROUTING_ENABLE", "1")
    monkeypatch.setenv("WHAT_DESKTOP_ROUTING_BACKEND", "coreaudio_aggregate")
    monkeypatch.setattr(arm, "_coreaudio_helper_path", lambda: "")

    status = arm.probe_routing(state_dir=tmp_path)
    assert status["backend"] == "coreaudio_aggregate"
    assert status["can_route"] is False
    assert "missing_coreaudio_helper" in status["blockers"]
    result = arm.ensure_routing(Path("."), state_dir=tmp_path)
    assert result["ok"] is False
    assert result["error"] == "missing_coreaudio_helper"


def test_coreaudio_probe_timeout_contract(monkeypatch, tmp_path):
    monkeypatch.setattr(arm, "_is_mac", lambda: True)
    monkeypatch.setenv("WHAT_DESKTOP_ROUTING_ENABLE", "1")
    monkeypatch.setenv("WHAT_DESKTOP_ROUTING_BACKEND", "coreaudio_aggregate")
    monkeypatch.setattr(arm, "_coreaudio_helper_path", lambda: "/tmp/what-coreaudio-routing")
    monkeypatch.setattr(
        arm,
        "_run_coreaudio_helper",
        lambda _helper, _command, state_dir, timeout_s=1.5: {
            "ok": False,
            "error": "coreaudio_helper_timeout",
            "detail": "timed out waiting for coreaudio helper",
        },
    )

    status = arm.probe_routing(state_dir=tmp_path)
    assert status["backend"] == "coreaudio_aggregate"
    assert status["ready"] is False
    assert status["can_route"] is True
    assert "coreaudio_probe_timeout" in status["blockers"]
    assert status["manual_steps"] == [
        "Retry in a moment.",
        "If this persists, run desktop install/uninstall once to collect helper error details.",
    ]


def test_coreaudio_backend_uses_helper(monkeypatch, tmp_path):
    monkeypatch.setattr(arm, "_is_mac", lambda: True)
    monkeypatch.setenv("WHAT_DESKTOP_ROUTING_ENABLE", "1")
    monkeypatch.setenv("WHAT_DESKTOP_ROUTING_BACKEND", "coreaudio_aggregate")
    monkeypatch.setattr(arm, "_coreaudio_helper_path", lambda: "/tmp/what-coreaudio-routing")

    def fake_helper(
        _helper,
        command,
        state_dir,
        expected_name="what-desktop",
        fallback_pattern="blackhole",
        timeout_s=90.0,
    ):
        _ = timeout_s
        if command == "probe":
            return {
                "ok": True,
                "routing": {
                    "backend": "coreaudio_aggregate",
                    "supported": True,
                    "enabled": True,
                    "can_route": True,
                    "can_restore": False,
                    "ready": False,
                    "name_expected": expected_name,
                    "manager_path": "/tmp/what-coreaudio-routing",
                    "target_output": "what-desktop",
                    "current_output": "Built-in Output",
                    "blockers": [],
                    "manual_steps": [],
                },
            }
        if command == "ensure":
            return {
                "ok": True,
                "changed": True,
                "routing": {
                    "backend": "coreaudio_aggregate",
                    "ready": True,
                    "target_output": "what-desktop",
                },
            }
        return {
            "ok": True,
            "changed": False,
            "routing": {"backend": "coreaudio_aggregate"},
        }

    monkeypatch.setattr(arm, "_run_coreaudio_helper", fake_helper)
    status = arm.probe_routing(state_dir=tmp_path)
    assert status["backend"] == "coreaudio_aggregate"
    assert status["can_route"] is True
    result = arm.ensure_routing(Path("."), state_dir=tmp_path)
    assert result["ok"] is True
    assert result["changed"] is True


def test_coreaudio_backend_ready_with_blackhole_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(arm, "_is_mac", lambda: True)
    monkeypatch.setenv("WHAT_DESKTOP_ROUTING_ENABLE", "1")
    monkeypatch.setenv("WHAT_DESKTOP_ROUTING_BACKEND", "coreaudio_aggregate")
    monkeypatch.setattr(arm, "_coreaudio_helper_path", lambda: "/tmp/what-coreaudio-routing")

    calls = {"probe": 0, "ensure": 0}

    def fake_helper(
        _helper,
        command,
        state_dir,
        expected_name="what-desktop",
        fallback_pattern="blackhole",
        timeout_s=90.0,
    ):
        _ = (state_dir, expected_name, fallback_pattern, timeout_s)
        if command == "probe":
            calls["probe"] += 1
            return {
                "ok": True,
                "routing": {
                    "backend": "coreaudio_aggregate",
                    "supported": True,
                    "enabled": True,
                    "can_route": True,
                    "can_restore": False,
                    "ready": True,
                    "name_expected": expected_name,
                    "manager_path": "/tmp/what-coreaudio-routing",
                    "target_output": "BlackHole 2ch",
                    "current_output": "BlackHole 2ch",
                    "target_is_expected": False,
                    "note": "Using BlackHole fallback for capture reliability.",
                    "blockers": [],
                    "manual_steps": [],
                },
            }
        if command == "ensure":
            calls["ensure"] += 1
            return {
                "ok": True,
                "changed": False,
                "routing": {
                    "backend": "coreaudio_aggregate",
                    "ready": True,
                    "target_output": "BlackHole 2ch",
                    "current_output": "BlackHole 2ch",
                    "target_is_expected": False,
                },
            }
        return {"ok": False, "error": "invalid_command"}

    monkeypatch.setattr(arm, "_run_coreaudio_helper", fake_helper)
    status = arm.probe_routing(state_dir=tmp_path)
    assert status["backend"] == "coreaudio_aggregate"
    assert status["ready"] is True
    assert status["target_output"] == "BlackHole 2ch"
    assert status["target_is_expected"] is False

    result = arm.ensure_routing(Path("."), state_dir=tmp_path)
    assert result["ok"] is True
    assert result["changed"] is False
    assert calls["ensure"] == 1


def test_coreaudio_ensure_retries_after_timeout(monkeypatch, tmp_path):
    monkeypatch.setattr(arm, "_is_mac", lambda: True)
    monkeypatch.setenv("WHAT_DESKTOP_ROUTING_ENABLE", "1")
    monkeypatch.setenv("WHAT_DESKTOP_ROUTING_BACKEND", "coreaudio_aggregate")
    monkeypatch.setenv("WHAT_COREAUDIO_HELPER_RETRY_ON_TIMEOUT", "1")
    monkeypatch.setattr(arm, "_coreaudio_helper_path", lambda: "/tmp/what-coreaudio-routing")

    calls = {"probe": 0, "ensure": 0}

    def fake_helper(
        _helper,
        command,
        state_dir,
        expected_name="what-desktop",
        fallback_pattern="blackhole",
        timeout_s=90.0,
    ):
        _ = (state_dir, expected_name, fallback_pattern, timeout_s)
        if command == "probe":
            calls["probe"] += 1
            return {
                "ok": True,
                "routing": {
                    "backend": "coreaudio_aggregate",
                    "supported": True,
                    "enabled": True,
                    "can_route": True,
                    "can_restore": False,
                    "ready": False,
                    "name_expected": "what-desktop",
                    "manager_path": "/tmp/what-coreaudio-routing",
                    "target_output": "what-desktop",
                    "current_output": "Built-in Output",
                    "blockers": [],
                    "manual_steps": [],
                },
            }
        if command == "ensure":
            calls["ensure"] += 1
            if calls["ensure"] == 1:
                return {"ok": False, "error": "coreaudio_helper_timeout"}
            return {
                "ok": True,
                "changed": True,
                "routing": {
                    "backend": "coreaudio_aggregate",
                    "ready": True,
                    "target_output": "what-desktop",
                },
            }
        return {"ok": False, "error": "invalid_command"}

    monkeypatch.setattr(arm, "_run_coreaudio_helper", fake_helper)
    result = arm.ensure_routing(Path("."), state_dir=tmp_path)
    assert result["ok"] is True
    assert result["changed"] is True
    assert calls["ensure"] == 2


def test_coreaudio_ensure_passthrough_fields(monkeypatch, tmp_path):
    monkeypatch.setattr(arm, "_is_mac", lambda: True)
    monkeypatch.setenv("WHAT_DESKTOP_ROUTING_ENABLE", "1")
    monkeypatch.setenv("WHAT_DESKTOP_ROUTING_BACKEND", "coreaudio_aggregate")
    monkeypatch.setattr(arm, "_coreaudio_helper_path", lambda: "/tmp/what-coreaudio-routing")

    def fake_helper(
        _helper,
        command,
        state_dir,
        expected_name="what-desktop",
        fallback_pattern="blackhole",
        timeout_s=90.0,
    ):
        _ = (state_dir, expected_name, fallback_pattern, timeout_s)
        if command == "probe":
            return {
                "ok": True,
                "routing": {
                    "backend": "coreaudio_aggregate",
                    "supported": True,
                    "enabled": True,
                    "can_route": True,
                    "ready": False,
                },
            }
        if command == "ensure":
            return {
                "ok": False,
                "error": "coreaudio_helper_exec_failed",
                "changed": False,
                "stderr": "x-stderr",
                "stdout": "x-stdout",
                "detail": "x-detail",
                "exit_code": 9,
                "code": 9,
                "aggregate": {"name": "what-desktop"},
                "routing": {"backend": "coreaudio_aggregate", "ready": False},
            }
        return {"ok": False, "error": "invalid_command"}

    monkeypatch.setattr(arm, "_run_coreaudio_helper", fake_helper)
    result = arm.ensure_routing(Path("."), state_dir=tmp_path)
    assert result["ok"] is False
    assert result["error"] == "coreaudio_helper_exec_failed"
    assert result["stderr"] == "x-stderr"
    assert result["stdout"] == "x-stdout"
    assert result["detail"] == "x-detail"
    assert result["exit_code"] == 9
    assert result["code"] == 9
    assert result["aggregate"] == {"name": "what-desktop"}
