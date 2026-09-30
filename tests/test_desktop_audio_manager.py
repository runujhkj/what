import json
import subprocess
from pathlib import Path

from what.controller import desktop_audio_manager as dam


def test_get_status_unsupported_platform(monkeypatch, tmp_path):
    monkeypatch.setattr(dam, "_is_mac", lambda: False)
    status = dam.get_status(tmp_path, tmp_path / "receipt.json")
    assert status["supported"] is False
    assert status["installed"] is False
    assert "macOS-only" in status["note"]


def test_get_status_installed_unmanaged(monkeypatch, tmp_path):
    monkeypatch.setattr(dam, "_is_mac", lambda: True)
    monkeypatch.setattr(dam, "_find_installed_loopback_drivers", lambda: ["BlackHole2ch.driver"])
    monkeypatch.setattr(dam, "_read_json", lambda _p: None)
    monkeypatch.setattr(dam, "_resolve_pkg", lambda _root: None)
    status = dam.get_status(tmp_path, tmp_path / "receipt.json")
    assert status["supported"] is True
    assert status["installed"] is True
    assert status["managed_install"] is False
    assert status["can_auto_uninstall"] is False
    assert "unmanaged" in status["note"].lower()


def test_get_status_managed_with_pkg(monkeypatch, tmp_path):
    monkeypatch.setattr(dam, "_is_mac", lambda: True)
    monkeypatch.setattr(dam, "_find_installed_loopback_drivers", lambda: ["BlackHole2ch.driver"])
    monkeypatch.setattr(
        dam,
        "_read_json",
        lambda _p: {"installed_by_controller": True, "managed_drivers": ["BlackHole2ch.driver"]},
    )
    monkeypatch.setattr(dam, "_resolve_pkg", lambda _root: Path("/tmp/BlackHole2ch.pkg"))
    status = dam.get_status(tmp_path, tmp_path / "receipt.json")
    assert status["managed_install"] is True
    assert status["can_auto_uninstall"] is True
    assert status["can_auto_install"] is True
    assert status["install_pkg_path"] == str(Path("/tmp/BlackHole2ch.pkg"))
    assert isinstance(status.get("routing"), dict)


def test_get_status_allows_uninstall_when_routing_output_present(monkeypatch, tmp_path):
    monkeypatch.setattr(dam, "_is_mac", lambda: True)
    monkeypatch.setattr(dam, "_find_installed_loopback_drivers", lambda: [])
    monkeypatch.setattr(dam, "_read_json", lambda _p: None)
    monkeypatch.setattr(dam, "_resolve_pkg", lambda _root: Path("/tmp/BlackHole2ch.pkg"))
    monkeypatch.setattr(
        dam.audio_routing_manager,
        "probe_routing",
        lambda state_dir=None: {
            "enabled": True,
            "ready": False,
            "name_expected": "what-desktop",
            "target_output": "what-desktop",
            "current_output": "what-desktop",
        },
    )
    status = dam.get_status(tmp_path, tmp_path / "receipt.json")
    assert status["installed"] is False
    assert status["managed_install"] is False
    assert status["can_auto_uninstall"] is True


def test_install_missing_pkg(monkeypatch, tmp_path):
    monkeypatch.setattr(dam, "_is_mac", lambda: True)
    monkeypatch.setattr(dam, "_find_installed_loopback_drivers", lambda: [])
    monkeypatch.setattr(dam, "_read_json", lambda _p: None)
    monkeypatch.setattr(dam, "_resolve_pkg", lambda _root: None)
    result = dam.install(tmp_path, tmp_path / "receipt.json")
    assert result["ok"] is False
    assert result["error"] == "missing_pkg"


def test_install_unmanaged_existing_adopts_without_admin(monkeypatch, tmp_path):
    called = {"run_admin": 0}

    def fake_run_admin(_cmd):
        called["run_admin"] += 1
        return subprocess.CompletedProcess(args=["osascript"], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(dam, "_is_mac", lambda: True)
    monkeypatch.setattr(dam, "_find_installed_loopback_drivers", lambda: ["BlackHole2ch.driver"])
    monkeypatch.setattr(dam, "_resolve_pkg", lambda _root: Path("/tmp/BlackHole2ch.pkg"))
    monkeypatch.setattr(dam, "_run_admin", fake_run_admin)
    monkeypatch.setattr(
        dam.audio_routing_manager,
        "ensure_routing",
        lambda _root, state_dir=None: {"ok": True, "changed": False, "routing": {"enabled": True, "ready": True}},
    )
    result = dam.install(tmp_path, tmp_path / "receipt.json")
    assert result["ok"] is True
    assert result["changed"] is False
    assert result["adopted_existing_install"] is True
    assert result["status"]["managed_install"] is True
    assert called["run_admin"] == 0


def test_install_managed_existing_runs_routing_ensure_without_admin(monkeypatch, tmp_path):
    called = {"run_admin": 0}
    routing_called = {"ensure": 0}

    def fake_run_admin(_cmd):
        called["run_admin"] += 1
        return subprocess.CompletedProcess(args=["osascript"], returncode=0, stdout="", stderr="")

    def fake_ensure(_root, state_dir=None):
        _ = state_dir
        routing_called["ensure"] += 1
        return {"ok": True, "changed": False, "routing": {"enabled": True, "ready": False}}

    monkeypatch.setattr(dam, "_is_mac", lambda: True)
    monkeypatch.setattr(dam, "_find_installed_loopback_drivers", lambda: ["BlackHole2ch.driver"])
    monkeypatch.setattr(
        dam,
        "_read_json",
        lambda _p: {"installed_by_controller": True, "managed_drivers": ["BlackHole2ch.driver"]},
    )
    monkeypatch.setattr(dam, "_resolve_pkg", lambda _root: Path("/tmp/BlackHole2ch.pkg"))
    monkeypatch.setattr(dam, "_run_admin", fake_run_admin)
    monkeypatch.setattr(dam.audio_routing_manager, "ensure_routing", fake_ensure)

    result = dam.install(tmp_path, tmp_path / "receipt.json")
    assert result["ok"] is True
    assert result["changed"] is False
    assert result["routing_ok"] is True
    assert result["status"]["managed_install"] is True
    assert called["run_admin"] == 0
    assert routing_called["ensure"] == 1


def test_install_success_writes_receipt(monkeypatch, tmp_path):
    monkeypatch.setattr(dam, "_is_mac", lambda: True)
    monkeypatch.setattr(dam, "_resolve_pkg", lambda _root: Path("/tmp/BlackHole2ch.pkg"))
    monkeypatch.setattr(dam, "_read_json", lambda _p: None)
    state = {"step": 0}

    def fake_find():
        if state["step"] == 0:
            return []
        return ["BlackHole2ch.driver"]

    def fake_run_admin(_cmd):
        state["step"] = 1
        return subprocess.CompletedProcess(args=["osascript"], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(dam, "_find_installed_loopback_drivers", fake_find)
    monkeypatch.setattr(dam, "_run_admin", fake_run_admin)

    receipt = tmp_path / "receipt.json"
    result = dam.install(tmp_path, receipt)
    assert result["ok"] is True
    assert result["changed"] is True
    data = json.loads(receipt.read_text(encoding="utf-8"))
    assert data["installed_by_controller"] is True
    assert "BlackHole2ch.driver" in data["managed_drivers"]


def test_uninstall_without_managed_install_runs_routing_cleanup(monkeypatch, tmp_path):
    monkeypatch.setattr(dam, "_is_mac", lambda: True)
    monkeypatch.setattr(dam, "_find_installed_loopback_drivers", lambda: [])
    monkeypatch.setattr(dam, "_read_json", lambda _p: None)
    monkeypatch.setattr(dam, "_resolve_pkg", lambda _root: None)
    monkeypatch.setattr(
        dam.audio_routing_manager,
        "remove_managed_routing",
        lambda _root, state_dir=None: {
            "ok": True,
            "changed": True,
            "routing": {"enabled": True, "ready": False, "name_expected": "what-desktop"},
        },
    )
    result = dam.uninstall(tmp_path, tmp_path / "receipt.json")
    assert result["ok"] is True
    assert result["changed"] is True
    assert result["routing_ok"] is True


def test_uninstall_success_removes_receipt(monkeypatch, tmp_path):
    monkeypatch.setattr(dam, "_is_mac", lambda: True)
    receipt = tmp_path / "receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "version": 1,
                "installed_by_controller": True,
                "managed_drivers": ["BlackHole2ch.driver"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(dam, "_find_installed_loopback_drivers", lambda: ["BlackHole2ch.driver"])
    monkeypatch.setattr(dam, "_resolve_pkg", lambda _root: None)
    monkeypatch.setattr(
        dam,
        "_run_admin",
        lambda _cmd: subprocess.CompletedProcess(args=["osascript"], returncode=0, stdout="", stderr=""),
    )

    result = dam.uninstall(tmp_path, receipt)
    assert result["ok"] is True
    assert result["changed"] is True
    assert receipt.exists() is False


def test_install_wires_routing_result(monkeypatch, tmp_path):
    monkeypatch.setattr(dam, "_is_mac", lambda: True)
    monkeypatch.setattr(dam, "_resolve_pkg", lambda _root: Path("/tmp/BlackHole2ch.pkg"))
    monkeypatch.setattr(dam, "_read_json", lambda _p: None)
    state = {"step": 0}

    def fake_find():
        if state["step"] == 0:
            return []
        return ["BlackHole2ch.driver"]

    def fake_run_admin(_cmd):
        state["step"] = 1
        return subprocess.CompletedProcess(args=["osascript"], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(dam, "_find_installed_loopback_drivers", fake_find)
    monkeypatch.setattr(dam, "_run_admin", fake_run_admin)
    monkeypatch.setattr(
        dam.audio_routing_manager,
        "ensure_routing",
        lambda _root, state_dir=None: {
            "ok": True,
            "changed": False,
            "routing": {"enabled": True, "ready": False, "name_expected": "what-desktop"},
        },
    )

    receipt = tmp_path / "receipt.json"
    result = dam.install(tmp_path, receipt)
    assert result["ok"] is True
    assert result["routing_changed"] is False
    assert result["routing_ok"] is True
    assert result["routing_error"] == ""
    assert result["routing"]["enabled"] is True


def test_install_driver_only_skips_routing(monkeypatch, tmp_path):
    monkeypatch.setattr(dam, "_is_mac", lambda: True)
    monkeypatch.setattr(dam, "_resolve_pkg", lambda _root: Path("/tmp/BlackHole2ch.pkg"))
    monkeypatch.setattr(dam, "_read_json", lambda _p: None)
    state = {"step": 0}

    def fake_find():
        if state["step"] == 0:
            return []
        return ["BlackHole2ch.driver"]

    def fake_run_admin(_cmd):
        state["step"] = 1
        return subprocess.CompletedProcess(args=["osascript"], returncode=0, stdout="", stderr="")

    called = {"ensure": 0}

    def fake_ensure(_root, state_dir=None):
        called["ensure"] += 1
        return {"ok": True, "changed": False, "routing": {"enabled": True, "ready": True}}

    monkeypatch.setattr(dam, "_find_installed_loopback_drivers", fake_find)
    monkeypatch.setattr(dam, "_run_admin", fake_run_admin)
    monkeypatch.setattr(dam.audio_routing_manager, "ensure_routing", fake_ensure)

    receipt = tmp_path / "receipt.json"
    result = dam.install(tmp_path, receipt, configure_routing=False)
    assert result["ok"] is True
    assert result["changed"] is True
    assert result["configure_routing"] is False
    assert result["routing_ok"] is True
    assert called["ensure"] == 0
