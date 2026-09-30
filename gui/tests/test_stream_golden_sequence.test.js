const assert = require("assert");
const runtime = require("../lib/main_overlay_test_stream_runtime");

function createRuntimeWithGoldenConfig(onPayload) {
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
    maxSegments: 7,
    linesLimit: 7,
    maxChars: 280,
    widthPx: 870,
    heightPx: 270,
    fontUi: 5.9,
    paddingPx: 6,
    maxLineChars: 31,
    noWordSplit: true,
  });
  inst.setConstraints({
    box: "desktop",
    maxSegments: 3,
    linesLimit: 3,
    maxChars: 280,
    widthPx: 510,
    heightPx: 500,
    fontUi: 11.15,
    paddingPx: 6,
    maxLineChars: 31,
    noWordSplit: true,
  });
  inst.setEnabled(true, "mic");
  inst.setEnabled(true, "desktop");
  return { inst, tick: () => timerFn && timerFn() };
}

function testGoldenSequenceTs1ToTs12() {
  const payloads = [];
  const { tick } = createRuntimeWithGoldenConfig((payload) => payloads.push(payload));
  for (let i = 0; i < 12; i += 1) tick();
  assert.strictEqual(payloads.length, 12);

  const expected = {
    1: { mic: ["test segment 1"], desktop: [] },
    2: { mic: ["test segment 1"], desktop: ["test segment 2"] },
    3: { mic: ["test segment 1 test segment 3"], desktop: ["test segment 2"] },
    4: { mic: ["test segment 1 test segment 3"], desktop: ["test segment 2 test segment 4"] },
    5: { mic: ["test segment 1 test segment 3", "test segment 5"], desktop: ["test segment 2 test segment 4"] },
    6: { mic: ["test segment 1 test segment 3", "test segment 5"], desktop: ["test segment 2 test segment 4", "test segment 6"] },
    7: { mic: ["test segment 1 test segment 3", "test segment 5 test segment 7"], desktop: ["test segment 2 test segment 4", "test segment 6"] },
    8: { mic: ["test segment 1 test segment 3", "test segment 5 test segment 7"], desktop: ["test segment 6 test segment 8"] },
    9: { mic: ["test segment 1 test segment 3", "test segment 5 test segment 7", "test segment 9"], desktop: ["test segment 6 test segment 8"] },
    10: { mic: ["test segment 1 test segment 3", "test segment 5 test segment 7", "test segment 9"], desktop: ["test segment 6 test segment 8", "test segment 10"] },
    11: { mic: ["test segment 1 test segment 3", "test segment 5 test segment 7", "test segment 9 test segment 11"], desktop: ["test segment 6 test segment 8", "test segment 10"] },
    12: { mic: ["test segment 1 test segment 3", "test segment 5 test segment 7", "test segment 9 test segment 11"], desktop: ["test segment 10 test segment 12"] },
  };

  for (let i = 0; i < payloads.length; i += 1) {
    const ts = i + 1;
    const p = payloads[i];
    assert.strictEqual(p.seq, ts, `seq mismatch at ts${ts}`);
    assert.strictEqual(p.trace_id, `main-test-${ts}`, `trace mismatch at ts${ts}`);
    assert.deepStrictEqual(
      p.boxes.mic.lines,
      expected[ts].mic,
      `mic lines mismatch at ts${ts}`
    );
    assert.deepStrictEqual(
      p.boxes.desktop.lines,
      expected[ts].desktop,
      `desktop lines mismatch at ts${ts}`
    );
  }
}

function testGoldenRoutingAndLimitsInvariants() {
  const payloads = [];
  const { tick } = createRuntimeWithGoldenConfig((payload) => payloads.push(payload));
  for (let i = 0; i < 12; i += 1) tick();
  const last = payloads[payloads.length - 1];
  assert.ok(last.boxes.mic.text.includes("11"));
  assert.ok(last.boxes.desktop.text.includes("12"));
  assert.ok(last.boxes.desktop.lines.length <= 3);
  assert.ok(last.boxes.mic.lines.length <= 7);
}

testGoldenSequenceTs1ToTs12();
testGoldenRoutingAndLimitsInvariants();
console.log("test_stream_golden_sequence.test.js: ok");
