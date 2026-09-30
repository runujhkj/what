import os
import sys
from pathlib import Path

import pytest

from what.controller import desktop_audio_manager as dam


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only desktop audio manager")
def test_live_install_uninstall_cycle_opt_in(tmp_path):
    """Manual/opt-in live test; may trigger admin password prompt.

    Behavior target:
    - Do as much automated install/uninstall work as possible.
    - If blocked, fail with explicit manual remediation steps.
    """
    if os.environ.get("WHAT_RUN_DESKTOP_ADMIN_TESTS", "").strip() != "1":
        pytest.skip("Set WHAT_RUN_DESKTOP_ADMIN_TESTS=1 to run live admin install/uninstall test.")

    repo_root = Path(__file__).resolve().parents[1]
    # Prefer controller receipt so live test aligns with GUI-managed state.
    default_receipt = Path.home() / ".what" / "controller_desktop_audio_receipt.json"
    receipt = default_receipt if default_receipt.exists() else (tmp_path / "controller_desktop_audio_receipt_live.json")
    status = dam.get_status(repo_root, receipt)
    actions: list[str] = []
    manual_steps: list[str] = []
    force_takeover = os.environ.get("WHAT_RUN_DESKTOP_ADMIN_TESTS_FORCE", "").strip() == "1"

    if not status.get("can_auto_install"):
        manual_steps.append(
            "Provide an installable pkg at assets/desktop-audio/BlackHole2ch.pkg "
            "or set WHAT_DESKTOP_AUDIO_PKG to a valid .pkg path."
        )
    if status.get("installed") and not status.get("managed_install") and not force_takeover:
        detected = ", ".join(status.get("installed_drivers", [])) or "<none>"
        manual_steps.append(
            f"Existing unmanaged loopback install detected ({detected}). "
            "Remove unmanaged loopback drivers manually, then rerun this test, "
            "or rerun with WHAT_RUN_DESKTOP_ADMIN_TESTS_FORCE=1 to let the test remove known loopback drivers."
        )
    if manual_steps:
        message = ["Desktop audio live automation is blocked before action:", ""] + [
            f"{idx}. {step}" for idx, step in enumerate(manual_steps, start=1)
        ]
        pytest.fail("\n".join(message))

    # Optional force-takeover path for unmanaged existing installs.
    if status.get("installed") and not status.get("managed_install") and force_takeover:
        installed = list(status.get("installed_drivers", []))
        targets = [
            str(dam.HAL_DIR / name)
            for name in installed
            if dam._is_known_loopback_driver(name)
        ]
        if not targets:
            pytest.fail(
                "Force mode requested, but no removable known loopback drivers were found in unmanaged install."
            )
        quoted = " ".join([dam._shell_quote_single(x) for x in targets])
        remove_result = dam._run_admin(f"rm -rf {quoted}")
        assert remove_result.returncode == 0, (
            "Force unmanaged removal failed.\n"
            f"stdout={remove_result.stdout}\n"
            f"stderr={remove_result.stderr}"
        )
        actions.append("force-remove(unmanaged) ok")
        status = dam.get_status(repo_root, receipt)
        if status.get("installed") and not status.get("managed_install"):
            pytest.fail(
                "Unmanaged loopback install is still detected after forced removal. "
                "Complete removal manually in /Library/Audio/Plug-Ins/HAL and rerun."
            )

    # Path A: managed install already present -> uninstall + reinstall.
    if status.get("managed_install"):
        uninstall_result = dam.uninstall(repo_root, receipt)
        assert uninstall_result.get("ok") is True, f"Managed uninstall failed: {uninstall_result}"
        actions.append("uninstall(managed) ok")

        install_result = dam.install(repo_root, receipt)
        assert install_result.get("ok") is True, f"Reinstall after uninstall failed: {install_result}"
        actions.append("reinstall(managed) ok")
        assert actions
        return

    # Path B: clean/not-installed -> install + uninstall + reinstall.
    install_result = dam.install(repo_root, receipt)
    assert install_result.get("ok") is True, f"Install failed: {install_result}"
    actions.append("install(clean) ok")

    uninstall_result = dam.uninstall(repo_root, receipt)
    assert uninstall_result.get("ok") is True, f"Uninstall after install failed: {uninstall_result}"
    actions.append("uninstall(after install) ok")

    reinstall_result = dam.install(repo_root, receipt)
    assert reinstall_result.get("ok") is True, f"Reinstall after cycle failed: {reinstall_result}"
    actions.append("reinstall(after cycle) ok")
    assert actions
