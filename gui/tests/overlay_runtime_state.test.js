const assert = require("assert");
const runtime = require("../lib/overlay_runtime_state");

function testCreateInitialOverlayPayload() {
  const payload = runtime.createInitialOverlayPayload();
  assert.strictEqual(payload.text, "");
  assert.deepStrictEqual(payload.lines, []);
  assert.strictEqual(payload.transition, "none");
  assert.strictEqual(payload.noWordSplit, true);
  assert.deepStrictEqual(payload.boxes, {});
}

function testNormalizeOverlayBoxKey() {
  assert.strictEqual(runtime.normalizeOverlayBoxKey(), "default");
  assert.strictEqual(runtime.normalizeOverlayBoxKey(""), "default");
  assert.strictEqual(runtime.normalizeOverlayBoxKey("all"), "default");
  assert.strictEqual(runtime.normalizeOverlayBoxKey("combined"), "default");
  assert.strictEqual(runtime.normalizeOverlayBoxKey("desktop"), "desktop");
  assert.strictEqual(runtime.normalizeOverlayBoxKey("mic"), "mic");
  assert.strictEqual(runtime.normalizeOverlayBoxKey("unknown"), "default");
}

function testOverlayPayloadForBox() {
  const payload = {
    text: "root",
    lines: ["root"],
    boxes: {
      mic: { text: "m", lines: ["m"] },
      desktop: { text: "d", lines: ["d"] }
    }
  };
  assert.strictEqual(runtime.overlayPayloadForBox(payload, "default").text, "root");
  assert.strictEqual(runtime.overlayPayloadForBox(payload, "mic").text, "m");
  assert.strictEqual(runtime.overlayPayloadForBox(payload, "desktop").text, "d");
  assert.strictEqual(runtime.overlayPayloadForBox(payload, "unknown").text, "root");
}

testCreateInitialOverlayPayload();
testNormalizeOverlayBoxKey();
testOverlayPayloadForBox();
console.log("overlay_runtime_state.test.js: ok");
