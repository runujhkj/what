const assert = require("assert");
const path = require("path");
const { registerDesktopIpcHandlers } = require("../lib/desktop_ipc_handlers");

function makeHarness() {
  const handlers = new Map();
  const ipcMain = {
    handle(name, fn) {
      handlers.set(name, fn);
    }
  };
  const app = {
    getPath(name) {
      assert.strictEqual(name, "userData");
      return "/tmp/state-dir";
    }
  };
  const calls = [];
  const desktopAudioProbe = {
    listDesktopDevices(backend) {
      calls.push(["listDesktopDevices", backend]);
      return Promise.resolve({ ok: true, backend });
    }
  };
  const desktopAudioManager = {
    getDesktopAudioManagerStatus(repoRoot, stateDir) {
      calls.push(["status", repoRoot, stateDir]);
      return Promise.resolve({ ok: true, action: "status" });
    },
    installDesktopAudioComponent(repoRoot, stateDir) {
      calls.push(["install", repoRoot, stateDir]);
      return Promise.resolve({ ok: true, action: "install" });
    },
    downloadDesktopAudioComponent(repoRoot, stateDir) {
      calls.push(["download", repoRoot, stateDir]);
      return Promise.resolve({ ok: true, action: "download" });
    },
    uninstallDesktopAudioComponent(repoRoot, stateDir) {
      calls.push(["uninstall", repoRoot, stateDir]);
      return Promise.resolve({ ok: true, action: "uninstall" });
    },
    reloadDesktopAudioDevices(repoRoot, stateDir) {
      calls.push(["reload", repoRoot, stateDir]);
      return Promise.resolve({ ok: true, action: "reload" });
    }
  };
  const audioRoutingManager = {
    getAudioRoutingStatus(stateDir) {
      calls.push(["routing-status", stateDir]);
      return Promise.resolve({ ok: true, action: "routing-status" });
    },
    applyDesktopAudioRouting(stateDir) {
      calls.push(["routing-apply", stateDir]);
      return Promise.resolve({ ok: true, action: "routing-apply" });
    },
    restoreDesktopAudioRouting(stateDir) {
      calls.push(["routing-restore", stateDir]);
      return Promise.resolve({ ok: true, action: "routing-restore" });
    }
  };
  return { handlers, ipcMain, app, calls, desktopAudioProbe, desktopAudioManager, audioRoutingManager };
}

async function testRegistrationAndDispatch() {
  const h = makeHarness();
  registerDesktopIpcHandlers({
    ipcMain: h.ipcMain,
    app: h.app,
    path,
    baseDir: "/repo/gui",
    desktopAudioProbe: h.desktopAudioProbe,
    desktopAudioManager: h.desktopAudioManager,
    audioRoutingManager: h.audioRoutingManager
  });

  const expected = [
    "list-desktop-devices",
    "desktop-audio-manager-status",
    "desktop-audio-manager-install",
    "desktop-audio-manager-download",
    "desktop-audio-manager-uninstall",
    "desktop-audio-manager-reload-audio",
    "audio-routing-status",
    "audio-routing-apply",
    "audio-routing-restore"
  ];
  expected.forEach((name) => assert.ok(h.handlers.has(name), `missing handler ${name}`));

  await h.handlers.get("list-desktop-devices")(null, "avfoundation");
  await h.handlers.get("desktop-audio-manager-status")();
  await h.handlers.get("desktop-audio-manager-install")();
  await h.handlers.get("desktop-audio-manager-download")();
  await h.handlers.get("desktop-audio-manager-uninstall")();
  await h.handlers.get("desktop-audio-manager-reload-audio")();
  await h.handlers.get("audio-routing-status")();
  await h.handlers.get("audio-routing-apply")();
  await h.handlers.get("audio-routing-restore")();

  const repoRoot = path.join("/repo/gui", "..");
  assert.deepStrictEqual(h.calls[0], ["listDesktopDevices", "avfoundation"]);
  assert.deepStrictEqual(h.calls[1], ["status", repoRoot, "/tmp/state-dir"]);
  assert.deepStrictEqual(h.calls[2], ["install", repoRoot, "/tmp/state-dir"]);
  assert.deepStrictEqual(h.calls[3], ["download", repoRoot, "/tmp/state-dir"]);
  assert.deepStrictEqual(h.calls[4], ["uninstall", repoRoot, "/tmp/state-dir"]);
  assert.deepStrictEqual(h.calls[5], ["reload", repoRoot, "/tmp/state-dir"]);
  assert.deepStrictEqual(h.calls[6], ["routing-status", "/tmp/state-dir"]);
  assert.deepStrictEqual(h.calls[7], ["routing-apply", "/tmp/state-dir"]);
  assert.deepStrictEqual(h.calls[8], ["routing-restore", "/tmp/state-dir"]);
}

async function run() {
  await testRegistrationAndDispatch();
  console.log("desktop_ipc_handlers.test.js: ok");
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});

