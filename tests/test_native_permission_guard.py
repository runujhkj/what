"""Run directly with the what venv; no ASR model or capture hardware needed."""
import asyncio
import threading
import unittest
from unittest.mock import patch
from unittest.mock import MagicMock
from types import SimpleNamespace

from what import native_desktop_helper as helper


class PermissionGuardTest(unittest.TestCase):
    def test_continuous_capture_yields_to_transport_callbacks(self):
        state = helper.HelperState(started_at=0)
        stop = threading.Event()
        ticks = []
        reads = []

        class Socket:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def send(self, value):
                if isinstance(value, str):
                    # Like websocket control-frame processing, this callback must
                    # run even when all PCM send calls complete synchronously.
                    asyncio.get_running_loop().call_soon(heartbeat)

        def heartbeat():
            ticks.append(len(reads))
            stop.set()

        def read(*args):
            reads.append(1)
            if len(reads) >= 100:
                stop.set()  # Bound failure if the loop starves callbacks again.
            return bytes([32, 0]) * 480

        proc = MagicMock()
        proc.stdout.fileno.return_value = 123
        with patch.object(helper.sys, "platform", "darwin"), \
                patch.object(helper, "_pair_token", return_value="test"), \
                patch("websockets.connect", return_value=Socket()), \
                patch.object(helper, "_start_coreaudio_tap_capture", return_value=proc), \
                patch.object(helper, "select", SimpleNamespace(select=lambda *args: ([123], [], []))), \
                patch.object(helper.os, "read", side_effect=read):
            asyncio.run(helper._stream_loop(
                state=state, stop_event=stop, service_host="localhost", service_port=8766,
                ws_path="/ingest", pair_path="/pair", transport="pcm",
                capture_mode="native-capture", desktop_device=""))
        self.assertTrue(ticks)
        self.assertLess(ticks[0], 100)
        proc.terminate.assert_called_once()

    def test_parent_app_permission_advice_replaces_standalone_helper_advice(self):
        error = "Operation not permitted: grant Screen Recording to WhatCoreAudioTap"
        message, permission = helper._capture_error_message(error, "Rantology")
        self.assertEqual(permission, "required")
        self.assertIn("Rantology", message)
        self.assertNotIn("WhatCoreAudioTap", message)
        standalone, _ = helper._capture_error_message(error)
        self.assertIn("WhatCoreAudioTap", standalone)

    def test_default_attempts_native_capture_despite_negative_python_preflight(self):
        state = helper.HelperState(started_at=0)
        stop = threading.Event()

        class Socket:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def send(self, value):
                pass

        async def run():
            task = asyncio.create_task(helper._stream_loop(
                state=state, stop_event=stop, service_host="localhost", service_port=8766,
                ws_path="/ingest", pair_path="/pair", transport="pcm",
                capture_mode="native-capture", desktop_device=""))
            try:
                await asyncio.sleep(0.65)  # Longer than the former automatic retry interval.
                self.assertEqual(state.capture_state, "failed")
                self.assertEqual(state.last_error, "native startup failed")
                self.assertEqual(state.retries, 1)
            finally:
                stop.set()
                await asyncio.wait_for(task, 1)

        with patch.object(helper.sys, "platform", "darwin"), \
                patch.object(helper, "_pair_token", return_value="test"), \
                patch("websockets.connect", return_value=Socket()), \
                patch.object(helper, "screen_capture_permitted", return_value=False) as preflight, \
                patch.object(helper, "_start_coreaudio_tap_capture",
                             side_effect=RuntimeError("native startup failed")) as capture:
            asyncio.run(run())
            preflight.assert_not_called()
            capture.assert_called_once()

    def test_denial_never_spawns_capture_or_retries(self):
        state = helper.HelperState(started_at=0)
        stop = threading.Event()

        class Socket:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def send(self, value):
                pass

        async def run():
            task = asyncio.create_task(helper._stream_loop(
                state=state, stop_event=stop, service_host="localhost", service_port=8766,
                ws_path="/ingest", pair_path="/pair", transport="pcm",
                capture_mode="native-capture", desktop_device="", permission_preflight=True))
            await asyncio.sleep(0.15)
            self.assertEqual(state.capture_state, "permission_required")
            self.assertEqual(state.retries, 1)
            stop.set()
            await asyncio.wait_for(task, 1)

        with patch.object(helper.sys, "platform", "darwin"), \
                patch.object(helper, "_pair_token", return_value="test"), \
                patch("websockets.connect", return_value=Socket()), \
                patch.object(helper, "screen_capture_permitted", return_value=False), \
                patch.object(helper, "_start_coreaudio_tap_capture") as capture:
            asyncio.run(run())
            capture.assert_not_called()


if __name__ == "__main__":
    unittest.main()
