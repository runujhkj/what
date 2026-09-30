import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import json
from pathlib import Path

import pytest

from what.audio import AudioConfig, InputConfig
from what.controller import audio_routing_manager as arm
from what.controller import desktop_audio_manager as dam
from what.controller.process import build_client_args
from what.live_audio_probe import measure_live_source
from what.controller.state import StreamSettings
from what.controller.types import ControllerConfig
from what.desktop_audio import list_desktop_devices


def _aggregate_helper_path() -> Path:
    return Path(__file__).resolve().parents[1] / "bin" / "what-coreaudio-aggregate"


def _run_aggregate_helper(args: list[str]) -> dict:
    helper = _aggregate_helper_path()
    if not helper.exists():
        return {"ok": False, "error": "missing_helper", "helper": str(helper)}
    try:
        result = subprocess.run(
            [str(helper), *args],
            capture_output=True,
            text=True,
            timeout=6,
        )
    except Exception as exc:
        return {"ok": False, "error": "exec_failed", "detail": str(exc)}
    out = str(result.stdout or "").strip()
    payload = {}
    if out:
        candidates = [out] + [ln.strip() for ln in out.splitlines() if ln.strip()]
        for candidate in reversed(candidates):
            try:
                decoded = json.loads(candidate)
                if isinstance(decoded, dict):
                    payload = decoded
                    break
            except Exception:
                continue
    if not payload:
        payload = {
            "ok": result.returncode == 0,
            "error": "invalid_output",
            "stdout": out,
            "stderr": str(result.stderr or ""),
        }
    return payload


def _pick_desktop_probe_candidates() -> tuple[list[str], list[str]]:
    devices = list_desktop_devices("avfoundation")
    preferred: list[str] = []
    for item in devices:
        text = str(item).lower()
        if "blackhole" in text:
            preferred.append(str(item))
    for item in devices:
        text = str(item).lower()
        if "what-desktop" in text:
            preferred.append(str(item))
    return devices, preferred


def _selector(label: str) -> str:
    m = re.match(r"^\s*(\d+)\s*:", label)
    return f":{m.group(1)}" if m else label


def _measure_desktop_signal_with_tone(preferred: list[str], output_mode: str) -> tuple[dict, str, str, list[str]]:
    restore_output_name = ""
    current = _run_aggregate_helper(["current-output"])
    if isinstance(current, dict) and current.get("ok"):
        restore_output_name = str(current.get("name") or "").strip()

    if output_mode in {"blackhole_only", "simultaneous"}:
        target_output = "BlackHole 2ch" if output_mode == "blackhole_only" else "what-desktop"
        switched = _run_aggregate_helper(["set-output", "--name", target_output])
        if not (isinstance(switched, dict) and switched.get("ok")):
            pytest.skip(f"Unable to set output for signal test mode={output_mode}: {switched}")
        time.sleep(0.25)

    diagnostics: list[str] = []
    measured = {"state": "error", "level": -1}
    picked = preferred[0]
    desktop_selector = _selector(picked)
    with tempfile.TemporaryDirectory() as td:
        tone_path = Path(td) / "tone.wav"
        gen = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=880:duration=2.4:sample_rate=48000",
                "-filter:a",
                "volume=6.0",
                "-ac",
                "2",
                "-ar",
                "48000",
                "-y",
                str(tone_path),
            ],
            capture_output=True,
            text=True,
            timeout=8,
        )
        assert gen.returncode == 0, f"Failed to generate tone file: {gen.stderr or gen.stdout}"
        player = subprocess.Popen(["afplay", str(tone_path)])
        try:
            time.sleep(0.2)
            for candidate in preferred:
                picked = candidate
                desktop_selector = _selector(candidate)
                for _ in range(8):
                    measured = measure_live_source(
                        "desktop",
                        InputConfig(
                            mode="desktop",
                            mic_backend="avfoundation",
                            mic_device="default",
                            mic_enabled=False,
                            desktop_backend="avfoundation",
                            desktop_device=desktop_selector,
                            desktop_enabled=True,
                            file_path="",
                            stdin_raw=False,
                        ),
                        AudioConfig(
                            sample_rate=48000,
                            channels=2,
                            frame_ms=20,
                            chunk_ms=500,
                            overlap_ms=0,
                        ),
                        duration_sec=0.7,
                    )
                    diagnostics.append(f"{candidate} ({desktop_selector}) => {measured}")
                    if measured.get("state") == "signal":
                        break
                    time.sleep(0.2)
                if measured.get("state") == "signal":
                    break
        finally:
            try:
                player.terminate()
                player.wait(timeout=1)
            except Exception:
                pass
            if output_mode in {"blackhole_only", "simultaneous"} and restore_output_name:
                _run_aggregate_helper(["set-output", "--name", restore_output_name])
    return measured, picked, desktop_selector, diagnostics


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only desktop audio mixed-flow live smoke")
def test_live_desktop_mic_mixed_flow_opt_in(tmp_path):
    """Opt-in smoke test for mixed desktop+mic capture wiring on macOS.

    Scope:
    - validates managed install/routing readiness using local system state
    - validates mixed stream args include both mic and desktop capture flags
    - validates desktop device inventory exposes the routed target label

    This does not assert transcript quality; it is a backend/routing wiring smoke.
    """
    if os.environ.get("WHAT_RUN_DESKTOP_ADMIN_TESTS", "").strip() != "1":
        pytest.skip("Set WHAT_RUN_DESKTOP_ADMIN_TESTS=1 to allow live desktop audio admin flow.")
    if os.environ.get("WHAT_RUN_DESKTOP_MIXED_LIVE", "").strip() != "1":
        pytest.skip("Set WHAT_RUN_DESKTOP_MIXED_LIVE=1 to run mixed desktop+mic live smoke.")

    repo_root = Path(__file__).resolve().parents[1]
    # Prefer the controller's real receipt path so live smoke aligns with the
    # user's current managed/unmanaged install state from the GUI.
    default_receipt = Path.home() / ".what" / "controller_desktop_audio_receipt.json"
    receipt = default_receipt if default_receipt.exists() else (tmp_path / "controller_desktop_audio_receipt_mixed_live.json")

    # Live smoke should validate the same routing path used by the app.
    os.environ.setdefault("WHAT_DESKTOP_ROUTING_ENABLE", "1")
    os.environ.setdefault("WHAT_DESKTOP_ROUTING_BACKEND", "coreaudio_aggregate")

    install_result = dam.install(repo_root, receipt)
    if not install_result.get("ok"):
        # If an existing unmanaged install is present, continue with status-based
        # validation rather than forcing destructive takeover in this smoke test.
        if str(install_result.get("error") or "") != "unmanaged_existing_install":
            assert install_result.get("ok") is True, (
                "Desktop audio install failed; complete install/setup first.\n"
                f"result={install_result}"
            )

    status = dam.get_status(repo_root, receipt)
    assert status.get("supported") is True
    assert status.get("installed") is True
    # This smoke should still pass if a pre-existing unmanaged install is used,
    # as long as routing/device checks below succeed.
    assert status.get("managed_install") in (True, False)

    routing = status.get("routing") or {}
    if routing.get("enabled"):
        assert routing.get("ready") is True, (
            "Desktop routing is not ready for mixed-flow smoke.\n"
            f"blockers={routing.get('blockers')}\n"
            f"manual_steps={routing.get('manual_steps')}\n"
            f"note={routing.get('note')}"
        )

    target_name = str(routing.get("target_output") or arm.EXPECTED_TARGET_NAME).strip()
    devices = list_desktop_devices("avfoundation")
    if not devices:
        pytest.fail(
            "No desktop devices returned by ffmpeg avfoundation probe. "
            "Confirm ffmpeg is installed and desktop devices are visible."
        )

    chosen_device = ""
    for entry in devices:
        if target_name and target_name.lower() in str(entry).lower():
            chosen_device = str(entry)
            break
    if not chosen_device:
        for entry in devices:
            if "blackhole" in str(entry).lower():
                chosen_device = str(entry)
                break
    if not chosen_device:
        pytest.fail(
            "No routed desktop device found in avfoundation list.\n"
            f"target={target_name}\n"
            f"devices={devices}"
        )

    cfg = ControllerConfig(
        host="127.0.0.1",
        port=8780,
        service_host="127.0.0.1",
        service_port=8765,
        config_path=None,
    )
    args = build_client_args(
        cfg,
        StreamSettings(
            input_mode="mic",
            mic_enabled=True,
            mic_backend="avfoundation",
            mic_device="default",
            desktop_enabled=True,
            desktop_backend="avfoundation",
            desktop_device=chosen_device,
            event_prefix="EVENT:",
        ),
    )

    assert "--mic-enabled" in args
    assert "--desktop-enabled" in args
    assert "--no-mic" not in args
    assert "--no-desktop" not in args
    assert "--desktop-device" in args
    assert chosen_device in args


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only desktop audio signal smoke")
def test_live_desktop_output_signal_detected():
    """Play a short tone to current desktop output and verify desktop probe sees signal.

    This validates end-to-end desktop loopback signal presence at the backend probe
    layer. It does not validate transcript text output.
    """
    if shutil.which("afplay") is None:
        pytest.skip("afplay not available")
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not available")

    # Decoupled from admin/install flows: require preconfigured routing readiness.
    os.environ.setdefault("WHAT_DESKTOP_ROUTING_ENABLE", "1")
    os.environ.setdefault("WHAT_DESKTOP_ROUTING_BACKEND", "coreaudio_aggregate")
    default_receipt = Path.home() / ".what" / "controller_desktop_audio_receipt.json"
    status = dam.get_status(Path(__file__).resolve().parents[1], default_receipt)
    routing = status.get("routing") or {}
    if not routing.get("enabled"):
        pytest.skip("Desktop routing manager is disabled; enable routing before signal smoke.")
    if routing.get("ready") is not True:
        pytest.skip(
            "Desktop routing is not ready for signal smoke. "
            f"blockers={routing.get('blockers')} manual_steps={routing.get('manual_steps')}"
        )

    # Probe available desktop devices and prefer loopback capture endpoint.
    # `what-desktop` is typically an output aggregate; BlackHole is the capture leg.
    devices, preferred = _pick_desktop_probe_candidates()
    if not devices:
        pytest.skip("No avfoundation desktop devices available")
    if not preferred:
        pytest.skip("No routed desktop loopback device found in avfoundation device list")

    # Optional output mode for test tone:
    # - WHAT_DESKTOP_SIGNAL_OUTPUT_MODE=blackhole_only -> route output directly to BlackHole 2ch
    # - WHAT_DESKTOP_SIGNAL_OUTPUT_MODE=simultaneous   -> route output to what-desktop (monitor+capture)
    # - WHAT_DESKTOP_SIGNAL_OUTPUT_MODE=default        -> keep current output selection
    # Default for this test is blackhole_only to isolate loopback capture.
    output_mode = os.environ.get("WHAT_DESKTOP_SIGNAL_OUTPUT_MODE", "").strip().lower() or "blackhole_only"
    measured, picked, desktop_selector, diagnostics = _measure_desktop_signal_with_tone(
        preferred, output_mode
    )

    assert measured.get("state") == "signal", (
        "Desktop probe did not detect signal while tone played.\n"
        f"output_mode={output_mode}\n"
        f"picked_device={picked}\n"
        f"desktop_selector={desktop_selector}\n"
        f"measured={measured}\n"
        f"devices={devices}\n"
        f"attempts={diagnostics}"
    )


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only desktop audio post-setup signal smoke")
def test_live_desktop_signal_after_setup_opt_in(tmp_path):
    """Opt-in live smoke: after setup/install, desktop signal should appear within a short window."""
    if os.environ.get("WHAT_RUN_DESKTOP_SIGNAL_AFTER_SETUP", "").strip() != "1":
        pytest.skip("Set WHAT_RUN_DESKTOP_SIGNAL_AFTER_SETUP=1 to run post-setup desktop signal smoke.")
    if shutil.which("afplay") is None or shutil.which("ffmpeg") is None:
        pytest.skip("afplay/ffmpeg required")

    repo_root = Path(__file__).resolve().parents[1]
    receipt = Path.home() / ".what" / "controller_desktop_audio_receipt.json"
    if not receipt.exists():
        receipt = tmp_path / "controller_desktop_audio_receipt_post_setup_live.json"

    os.environ.setdefault("WHAT_DESKTOP_ROUTING_ENABLE", "1")
    os.environ.setdefault("WHAT_DESKTOP_ROUTING_BACKEND", "coreaudio_aggregate")

    install_result = dam.install(repo_root, receipt)
    if not install_result.get("ok") and str(install_result.get("error") or "") != "unmanaged_existing_install":
        pytest.fail(f"desktop setup/install failed before signal probe: {install_result}")

    status = dam.get_status(repo_root, receipt)
    routing = status.get("routing") or {}
    if not routing.get("enabled"):
        pytest.skip("Desktop routing disabled")
    if routing.get("ready") is not True:
        pytest.skip(
            "Desktop routing not ready after setup/install.\n"
            f"blockers={routing.get('blockers')} manual_steps={routing.get('manual_steps')} note={routing.get('note')}"
        )

    devices, preferred = _pick_desktop_probe_candidates()
    if not devices or not preferred:
        pytest.skip(f"Desktop probe candidates unavailable after setup: devices={devices}")

    measured, picked, desktop_selector, diagnostics = _measure_desktop_signal_with_tone(
        preferred, "blackhole_only"
    )
    assert measured.get("state") == "signal", (
        "No desktop signal detected within post-setup window.\n"
        f"picked_device={picked}\n"
        f"desktop_selector={desktop_selector}\n"
        f"measured={measured}\n"
        f"devices={devices}\n"
        f"attempts={diagnostics}"
    )
