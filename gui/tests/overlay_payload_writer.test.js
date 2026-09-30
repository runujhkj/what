const assert = require("node:assert");
const writer = require("../lib/overlay_payload_writer");

(function testBuildOverlayPayloadEnvelope() {
  const payload = writer.buildOverlayPayload({
    seq: 42,
    traceId: "trace-42",
    rootText: "root",
    rootFullText: "root",
    rootLines: ["root"],
    animationMode: "none",
    rootConfig: { header: "", widthPx: 640, heightPx: 140, fontUi: 7.05, paddingPx: 6, noWordSplit: true },
    micText: "mic",
    micFullText: "mic",
    micLines: ["mic"],
    micConfig: { header: "Mic", widthPx: 870, heightPx: 270, fontUi: 5.9, paddingPx: 4, noWordSplit: true },
    desktopText: "desktop",
    desktopFullText: "desktop",
    desktopLines: ["desktop"],
    desktopConfig: { header: "Desktop", widthPx: 510, heightPx: 500, fontUi: 11.15, paddingPx: 4, noWordSplit: true },
  });
  assert.strictEqual(payload.seq, 42);
  assert.strictEqual(payload.trace_id, "trace-42");
  assert.strictEqual(payload.text, "root");
  assert.deepStrictEqual(payload.lines, ["root"]);
  assert.strictEqual(payload.boxes.mic.header, "Mic");
  assert.strictEqual(payload.boxes.desktop.header, "Desktop");
  assert.strictEqual(payload.boxes.mic.width, "870");
  assert.strictEqual(payload.boxes.desktop.fontSize, "11.15");
})();

console.log("overlay_payload_writer.test.js: ok");
