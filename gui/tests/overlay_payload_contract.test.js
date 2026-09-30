const assert = require("assert");
const contract = require("../lib/overlay_payload_contract");

function testNormalizeOverlayPayloadHeaderBodySeparation() {
  const normalized = contract.normalizeOverlayPayload({
    header: "Mic",
    text: "Mic",
    lines: ["Mic", "Mic: hello world"],
    boxes: {
      mic: {
        header: "Mic",
        text: "Mic: foo",
        lines: ["Mic", "Mic: foo"],
      },
      desktop: {
        header: "Desktop",
        text: "Desktop - bar",
        lines: ["Desktop", "Desktop - bar"],
      },
    },
  });

  assert.strictEqual(normalized.header, "Mic");
  assert.deepStrictEqual(normalized.lines, ["hello world"]);
  assert.strictEqual(normalized.text, "hello world");

  assert.ok(normalized.boxes.mic);
  assert.strictEqual(normalized.boxes.mic.header, "Mic");
  assert.deepStrictEqual(normalized.boxes.mic.lines, ["foo"]);
  assert.strictEqual(normalized.boxes.mic.text, "foo");

  assert.ok(normalized.boxes.desktop);
  assert.strictEqual(normalized.boxes.desktop.header, "Desktop");
  assert.deepStrictEqual(normalized.boxes.desktop.lines, ["bar"]);
  assert.strictEqual(normalized.boxes.desktop.text, "bar");
}

function testNormalizeOverlayPayloadDefaults() {
  const normalized = contract.normalizeOverlayPayload({});
  assert.strictEqual(normalized.text, "");
  assert.deepStrictEqual(normalized.lines, []);
  assert.strictEqual(normalized.transition, "none");
  assert.strictEqual(normalized.noWordSplit, true);
  assert.deepStrictEqual(normalized.boxes, {});
}

function testNormalizeOverlayPayloadPreservesMetadataAndFlags() {
  const normalized = contract.normalizeOverlayPayload({
    text: "Mic: alpha",
    lines: ["Mic: alpha"],
    transition: "roll",
    enterLine: "alpha",
    animationMode: "none",
    noWordSplit: false,
    boxes: {
      mic: {
        header: "Mic",
        text: "Mic: hello",
        lines: ["Mic: hello"],
        transition: "grow",
        enterLine: "hello",
        animationMode: "token_fade",
        noWordSplit: false,
        config: {
          maxSegments: "6",
          maxChars: "280",
          width: "870",
          height: "270",
          padding: "4",
          fontSize: "5.9",
        },
      },
    },
  });
  assert.strictEqual(normalized.transition, "roll");
  assert.strictEqual(normalized.enterLine, "alpha");
  assert.strictEqual(normalized.animationMode, "none");
  assert.strictEqual(normalized.noWordSplit, false);
  assert.ok(normalized.boxes.mic);
  assert.strictEqual(normalized.boxes.mic.transition, "grow");
  assert.strictEqual(normalized.boxes.mic.enterLine, "hello");
  assert.strictEqual(normalized.boxes.mic.animationMode, "token_fade");
  assert.strictEqual(normalized.boxes.mic.noWordSplit, false);
  assert.ok(normalized.boxes.mic.config);
  assert.strictEqual(normalized.boxes.mic.config.maxSegments, 6);
  assert.strictEqual(normalized.boxes.mic.config.maxChars, 280);
  assert.strictEqual(normalized.boxes.mic.config.width, 870);
  assert.strictEqual(normalized.boxes.mic.config.height, 270);
  assert.strictEqual(normalized.boxes.mic.config.padding, 4);
  assert.strictEqual(normalized.boxes.mic.config.fontSize, 5.9);
}

function testNormalizeOverlayPayloadDoesNotMutateInput() {
  const payload = {
    text: "Mic: one",
    lines: ["Mic: one"],
    boxes: {
      mic: {
        header: "Mic",
        text: "Mic: two",
        lines: ["Mic: two"],
      },
    },
  };
  const snapshot = JSON.stringify(payload);
  contract.normalizeOverlayPayload(payload);
  assert.strictEqual(JSON.stringify(payload), snapshot);
}

function testNormalizeOverlayPayloadStripsNonColonLabelPrefixes() {
  const normalized = contract.normalizeOverlayPayload({
    header: "Desktop",
    lines: ["Desktop hello world", "desktoping survives"],
    boxes: {
      desktop: {
        header: "Desktop",
        lines: ["Desktop one two", "Desktop: three four"],
      },
    },
  });

  assert.deepStrictEqual(normalized.lines, ["hello world", "desktoping survives"]);
  assert.deepStrictEqual(normalized.boxes.desktop.lines, ["one two", "three four"]);
}

testNormalizeOverlayPayloadHeaderBodySeparation();
testNormalizeOverlayPayloadDefaults();
testNormalizeOverlayPayloadPreservesMetadataAndFlags();
testNormalizeOverlayPayloadDoesNotMutateInput();
testNormalizeOverlayPayloadStripsNonColonLabelPrefixes();
console.log("overlay_payload_contract.test.js: ok");
