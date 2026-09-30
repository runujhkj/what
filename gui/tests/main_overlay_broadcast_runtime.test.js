const assert = require("assert");
const runtime = require("../lib/main_overlay_broadcast_runtime");

function testTelemetryAndFanout() {
  const logs = [];
  const writes = [];
  const payload = {
    seq: 12,
    trace_id: "main-test-12",
    lines: ["root one", "root two"],
    boxes: {
      mic: { lines: ["mic one"] },
      desktop: { lines: ["desk one"] },
    },
  };
  const overlayClients = new Map();
  overlayClients.set({ write: (line) => writes.push(["default", line]) }, "default");
  overlayClients.set({ write: (line) => writes.push(["desktop", line]) }, "desktop");

  const broadcast = runtime.createOverlayBroadcaster({
    getOverlayPayload: () => payload,
    overlayPayloadForBox: (boxKey, next) => {
      if (boxKey === "desktop") return { ...next, text: "desktop scoped" };
      return { ...next, text: "root scoped" };
    },
    overlayClients,
    encodeOverlay: (value) => JSON.stringify(value),
    log: (line) => logs.push(line),
  });

  broadcast();

  assert.strictEqual(logs.length, 1);
  assert.ok(logs[0].includes("broadcast payload seq=12"));
  assert.ok(logs[0].includes("trace='main-test-12'"));
  assert.ok(logs[0].includes("root_l=2"));
  assert.ok(logs[0].includes("mic_l=1"));
  assert.ok(logs[0].includes("desk_l=1"));
  assert.ok(logs[0].includes("clients=2"));

  assert.strictEqual(writes.length, 2);
  assert.ok(writes[0][1].includes("\"text\":\"root scoped\""));
  assert.ok(writes[1][1].includes("\"text\":\"desktop scoped\""));
}

function testWriteFailureIsolation() {
  const writes = [];
  const payload = {
    seq: 4,
    trace_id: "main-test-4",
    lines: [],
    boxes: { mic: { lines: [] }, desktop: { lines: [] } },
  };
  const overlayClients = new Map();
  overlayClients.set({ write: () => { throw new Error("boom"); } }, "default");
  overlayClients.set({ write: (line) => writes.push(line) }, "mic");
  const broadcast = runtime.createOverlayBroadcaster({
    getOverlayPayload: () => payload,
    overlayPayloadForBox: (_boxKey, next) => next,
    overlayClients,
    encodeOverlay: (value) => JSON.stringify(value),
    log: () => {},
  });

  assert.doesNotThrow(() => broadcast());
  assert.strictEqual(writes.length, 1);
  assert.ok(writes[0].startsWith("data: "));
}

function run() {
  testTelemetryAndFanout();
  testWriteFailureIsolation();
  console.log("main_overlay_broadcast_runtime.test.js: ok");
}

run();
