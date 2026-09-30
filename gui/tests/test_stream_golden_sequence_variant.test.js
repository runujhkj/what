const assert = require("assert");
const runtime = require("../lib/main_overlay_test_stream_runtime");

function createVariantRuntime(onPayload) {
  let timerFn = null;
  const inst = runtime.createLocalTestStreamRuntime({
    normalizeOverlayPayload: (v) => v,
    setIntervalFn: (fn) => {
      timerFn = fn;
      return 1;
    },
    clearIntervalFn: () => {},
    onPayload,
    onStateChange: () => {},
    linesLimit: 3,
    maxChars: 280,
  });
  inst.setConstraints({
    box: "mic",
    maxSegments: 4,
    linesLimit: 4,
    maxChars: 280,
    widthPx: 760,
    paddingPx: 6,
    fontUi: 6.5,
    maxLineChars: 18,
    noWordSplit: true,
  });
  inst.setConstraints({
    box: "desktop",
    maxSegments: 2,
    linesLimit: 2,
    maxChars: 280,
    widthPx: 420,
    paddingPx: 6,
    fontUi: 8.2,
    maxLineChars: 14,
    noWordSplit: true,
  });
  inst.setEnabled(true, "mic");
  inst.setEnabled(true, "desktop");
  return { tick: () => timerFn && timerFn() };
}

function testGoldenVariantTs1ToTs12() {
  const payloads = [];
  const { tick } = createVariantRuntime((payload) => payloads.push(payload));
  for (let i = 0; i < 12; i += 1) tick();
  assert.strictEqual(payloads.length, 12);

  const expectedMic = {
    1: ["test segment 1"],
    2: ["test segment 1"],
    3: ["test segment 1", "test segment 3"],
    4: ["test segment 1", "test segment 3"],
    5: ["test segment 1", "test segment 3", "test segment 5"],
    6: ["test segment 1", "test segment 3", "test segment 5"],
    7: ["test segment 1", "test segment 3", "test segment 5", "test segment 7"],
    8: ["test segment 1", "test segment 3", "test segment 5", "test segment 7"],
    9: ["test segment 3", "test segment 5", "test segment 7", "test segment 9"],
    10: ["test segment 3", "test segment 5", "test segment 7", "test segment 9"],
    11: ["test segment 5", "test segment 7", "test segment 9", "test segment 11"],
    12: ["test segment 5", "test segment 7", "test segment 9", "test segment 11"],
  };
  const expectedDesktop = {
    1: [],
    2: ["test segment 2"],
    3: ["test segment 2"],
    4: ["test segment 2", "test segment 4"],
    5: ["test segment 2", "test segment 4"],
    6: ["test segment 4", "test segment 6"],
    7: ["test segment 4", "test segment 6"],
    8: ["test segment 6", "test segment 8"],
    9: ["test segment 6", "test segment 8"],
    10: ["test segment", "10"],
    11: ["test segment", "10"],
    12: ["segment 12"],
  };

  for (let i = 0; i < payloads.length; i += 1) {
    const ts = i + 1;
    const p = payloads[i];
    assert.strictEqual(p.seq, ts, `seq mismatch at ts${ts}`);
    assert.strictEqual(p.trace_id, `main-test-${ts}`, `trace mismatch at ts${ts}`);
    assert.deepStrictEqual(p.boxes.mic.lines, expectedMic[ts], `mic mismatch at ts${ts}`);
    assert.deepStrictEqual(p.boxes.desktop.lines, expectedDesktop[ts], `desktop mismatch at ts${ts}`);
  }
}

testGoldenVariantTs1ToTs12();
console.log("test_stream_golden_sequence_variant.test.js: ok");
