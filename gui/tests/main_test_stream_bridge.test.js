const assert = require("assert");
const bridge = require("../lib/main_test_stream_bridge");

function testBooleanToggle() {
  const calls = [];
  const setOverlayTestStreamEnabled = bridge.createSetOverlayTestStreamEnabled({
    setConstraints: (value) => calls.push(["constraints", value]),
    setEnabled: (enabled, box) => calls.push(["enabled", enabled, box]),
    coerceEnabled: (value) => Boolean(value),
  });

  setOverlayTestStreamEnabled(true);
  assert.deepStrictEqual(calls, [["enabled", true, undefined]]);
}

function testObjectToggleWithConstraints() {
  const calls = [];
  const setOverlayTestStreamEnabled = bridge.createSetOverlayTestStreamEnabled({
    setConstraints: (value) => calls.push(["constraints", value]),
    setEnabled: (enabled, box) => calls.push(["enabled", enabled, box]),
    coerceEnabled: (value) => String(value).trim().toLowerCase() === "on",
  });

  setOverlayTestStreamEnabled({
    enabled: "on",
    box: "DESKTOP",
    linesLimit: 6,
    maxChars: 280,
    maxSegments: 9,
    widthPx: 510,
    paddingPx: 6,
    fontUi: 11.15,
    maxLineChars: 31,
  });

  assert.deepStrictEqual(calls[0], [
    "constraints",
    {
      box: "desktop",
      linesLimit: 6,
      maxChars: 280,
      maxSegments: 9,
      widthPx: 510,
      paddingPx: 6,
      fontUi: 11.15,
      maxLineChars: 31,
      noWordSplit: true,
    },
  ]);
  assert.deepStrictEqual(calls[1], ["enabled", true, "desktop"]);
}

function run() {
  testBooleanToggle();
  testObjectToggleWithConstraints();
  testInvalidNumericConstraintsAreIgnored();
  testNoWordSplitOnlyPayloadStillUpdatesConstraints();
  console.log("main_test_stream_bridge.test.js: ok");
}

function testInvalidNumericConstraintsAreIgnored() {
  const calls = [];
  const setOverlayTestStreamEnabled = bridge.createSetOverlayTestStreamEnabled({
    setConstraints: (value) => calls.push(["constraints", value]),
    setEnabled: (enabled, box) => calls.push(["enabled", enabled, box]),
    coerceEnabled: (value) => Boolean(value),
  });

  setOverlayTestStreamEnabled({
    enabled: true,
    box: "mic",
    linesLimit: "",
    maxChars: "",
    maxSegments: "",
    widthPx: "",
    paddingPx: "",
    fontUi: "",
    maxLineChars: "",
  });

  assert.deepStrictEqual(calls[0], ["enabled", true, "mic"]);
}

function testNoWordSplitOnlyPayloadStillUpdatesConstraints() {
  const calls = [];
  const setOverlayTestStreamEnabled = bridge.createSetOverlayTestStreamEnabled({
    setConstraints: (value) => calls.push(["constraints", value]),
    setEnabled: (enabled, box) => calls.push(["enabled", enabled, box]),
    coerceEnabled: (value) => Boolean(value),
  });

  setOverlayTestStreamEnabled({
    enabled: true,
    box: "desktop",
    noWordSplit: false,
  });

  assert.deepStrictEqual(calls[0], [
    "constraints",
    {
      box: "desktop",
      noWordSplit: false,
    },
  ]);
  assert.deepStrictEqual(calls[1], ["enabled", true, "desktop"]);
}

run();
