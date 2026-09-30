const assert = require("assert");
const fs = require("fs");
const path = require("path");

function parseHandledChannels(mainJsSource) {
  const channels = new Set();
  const re = /ipcMain\.handle\("([^"]+)"/g;
  let m = re.exec(mainJsSource);
  while (m) {
    channels.add(m[1]);
    m = re.exec(mainJsSource);
  }
  return channels;
}

function testMainIpcChannelsRemainStable() {
  const mainPath = path.join(__dirname, "..", "main.js");
  const src = fs.readFileSync(mainPath, "utf-8");
  const channels = parseHandledChannels(src);

  const expected = [
    "client-start",
    "client-stop",
    "client-status",
    "open-desktop-audio-stub",
    "get-ui-prefs",
    "set-ui-prefs"
  ];
  expected.forEach((name) => {
    assert.ok(channels.has(name), `missing ipc channel: ${name}`);
  });

  assert.ok(
    src.includes("desktopIpcHandlers.registerDesktopIpcHandlers("),
    "desktop IPC registration call removed"
  );
  assert.ok(
    src.includes("fileIpcHandlers.registerFileIpcHandlers("),
    "file IPC registration call removed"
  );
  assert.ok(
    src.includes("correctionsIpcHandlers.registerCorrectionsIpcHandlers("),
    "corrections IPC registration call removed"
  );
  assert.ok(
    src.includes("overlayIpcHandlers.registerOverlayIpcHandlers("),
    "overlay IPC registration call removed"
  );
  assert.ok(
    src.includes("overlayServerRuntimeFactory.createOverlayServerRuntime("),
    "overlay server runtime extraction removed"
  );
}

testMainIpcChannelsRemainStable();
console.log("ipc_registration_contract.test.js: ok");
