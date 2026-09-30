const assert = require("assert");
const startup = require("../lib/client_startup");

function testNormalizeDefaults() {
  const out = startup.normalizeClientOpts({});
  assert.strictEqual(out.host, "127.0.0.1");
  assert.strictEqual(out.port, 8765);
  assert.strictEqual(out.inputMode, "mic");
  assert.strictEqual(out.micEnabled, true);
  assert.strictEqual(out.desktopEnabled, false);
}

function testDecisionReuseSkipRestart() {
  const retry = startup.normalizeClientOpts({ micDevice: "default" });
  assert.strictEqual(startup.decideClientStart({ hasRunning: true, lastOpts: retry, nextOpts: retry, forceRestart: true }), "restart");
  const base = startup.normalizeClientOpts({ inputMode: "desktop", desktopEnabled: true });
  assert.strictEqual(
    startup.decideClientStart({ hasRunning: true, lastOpts: base, nextOpts: { ...base }, forceRestart: false }),
    "reuse"
  );
  assert.strictEqual(
    startup.decideClientStart({
      hasRunning: true,
      lastOpts: base,
      nextOpts: startup.normalizeClientOpts({ inputMode: "mic" }),
      forceRestart: false
    }),
    "skip"
  );
  assert.strictEqual(
    startup.decideClientStart({
      hasRunning: true,
      lastOpts: base,
      nextOpts: startup.normalizeClientOpts({ inputMode: "mic" }),
      forceRestart: true
    }),
    "restart"
  );
  assert.strictEqual(
    startup.decideClientStart({ hasRunning: false, lastOpts: null, nextOpts: base, forceRestart: false }),
    "start"
  );
}

function testBuildClientArgsMixedCapture() {
  const normalized = startup.normalizeClientOpts({
    inputMode: "mic",
    host: "127.0.0.1",
    port: 8765,
    micEnabled: true,
    micBackend: "avfoundation",
    micDevice: ":1",
    desktopEnabled: true,
    desktopBackend: "avfoundation",
    desktopDevice: ":2",
    eventPrefix: "EVENT:"
  });
  const args = startup.buildClientArgs(normalized);
  assert.deepStrictEqual(args.slice(0, 2), ["client", "--local"]);
  assert.ok(args.includes("--captions-on"));
  assert.strictEqual(args[args.indexOf("--input") + 1], "mic");
  assert.match(args[args.indexOf("--client-id") + 1], /^mic-[a-z0-9]+$/);
  assert.ok(args.includes("--mic-enabled"));
  assert.ok(args.includes("--desktop-enabled"));
  assert.ok(args.includes("--desktop-device"));
  assert.ok(args.includes(":2"));
  assert.ok(!args.includes("--no-mic"));
  assert.ok(!args.includes("--no-desktop"));
}

function testBuildClientArgsFileModeShape() {
  const none = startup.buildClientArgs(startup.normalizeClientOpts({
    inputMode: "file",
    filePath: "",
  }));
  assert.ok(none.includes("--input"));
  assert.ok(none.includes("file"));
  assert.ok(!none.includes("--file"));

  const withFile = startup.buildClientArgs(startup.normalizeClientOpts({
    inputMode: "file",
    filePath: "/tmp/example.wav",
    realtime: true,
  }));
  assert.ok(withFile.includes("--file"));
  assert.ok(withFile.includes("/tmp/example.wav"));
  assert.ok(withFile.includes("--realtime"));
}

function testDecisionRunningServiceWithDesktopToggleNeedsRestartWhenForced() {
  const last = startup.normalizeClientOpts({
    inputMode: "mic",
    micEnabled: true,
    desktopEnabled: false,
  });
  const next = startup.normalizeClientOpts({
    inputMode: "mic",
    micEnabled: true,
    desktopEnabled: true,
    desktopBackend: "avfoundation",
    desktopDevice: ":0",
  });
  assert.strictEqual(
    startup.decideClientStart({
      hasRunning: true,
      lastOpts: last,
      nextOpts: next,
      forceRestart: false,
    }),
    "skip"
  );
  assert.strictEqual(
    startup.decideClientStart({
      hasRunning: true,
      lastOpts: last,
      nextOpts: next,
      forceRestart: true,
    }),
    "restart"
  );
}

function run() {
  testNormalizeDefaults();
  testDecisionReuseSkipRestart();
  testBuildClientArgsMixedCapture();
  testBuildClientArgsFileModeShape();
  testDecisionRunningServiceWithDesktopToggleNeedsRestartWhenForced();
  console.log("client_startup.test.js: ok");
}

run();
