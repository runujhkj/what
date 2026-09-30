const test = require("node:test");
const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const path = require("node:path");

const LEGACY_TEST_FILES = [
  "caption_box_layout.test.js",
  "caption_box_page.test.js",
  "caption_box_view.test.js",
  "caption_box_stream.test.js",
  "live_caption_trace.test.js",
  "transcript_record.test.js",
  "review_audio.test.js",
  "linux_desktop_capture.test.js",
  "mic_devices.test.js",
  "windows_hide.test.js",
  "transcript_view.test.js",
  "session_corrections.test.js",
  "audio_defaults.test.js",
  "output_watch.test.js",
  "line_freeze_compositor.test.js",
  "line_fit_authority.test.js",
  "overlay_label_policy.test.js",
  "overlay_body_sanitizer.test.js",
  "overlay_payload_contract.test.js",
  "overlay_constraints_authority.test.js",
  "overlay_layout_budget_authority.test.js",
  "overlay_box_runtime.test.js",
  "overlay_payload_writer.test.js",
  "overlay_runtime_state.test.js",
  "main_test_stream_bridge.test.js",
  "main_overlay_ingest_gate.test.js",
  "main_overlay_broadcast_runtime.test.js",
  "main_overlay_test_stream_runtime.test.js",
  "test_stream_lane_policy.test.js",
  "test_stream_lane_pipeline.test.js",
  "test_stream_golden_sequence.test.js",
  "test_stream_golden_sequence_variant.test.js",
  "window_state_store.test.js",
  "ui_prefs_disk_store.test.js",
  "client_startup.test.js",
  "device_switching.test.js",
  "runtime_device_switching.test.js",
  "file_ipc_handlers.test.js",
  "corrections_ipc_handlers.test.js",
  "overlay_ipc_handlers.test.js",
  "overlay_server_runtime.test.js",
  "renderer_compat_state_machine_contract.test.js",
  "desktop_ipc_handlers.test.js",
  "ipc_registration_contract.test.js",
  "runtime_paths.test.js",
  "python_runtime.test.js",
  "session_loader.test.js",
  "session_workspace.test.js",
  "session_archive.test.js",
  "app_menu.test.js"
];

test("gui legacy test scripts pass", () => {
  for (const file of LEGACY_TEST_FILES) {
    const full = path.join(__dirname, file);
    const run = spawnSync(process.execPath, [full], { encoding: "utf-8" });
    assert.equal(
      run.status,
      0,
      `failed ${file}\nstdout:\n${run.stdout || ""}\nstderr:\n${run.stderr || ""}`
    );
  }
});
