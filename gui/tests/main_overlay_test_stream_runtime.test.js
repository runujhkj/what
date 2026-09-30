const assert = require("assert");
const runtime = require("../lib/main_overlay_test_stream_runtime");

function testAcceptancePolicy() {
  let out = runtime.shouldAcceptIncomingOverlayPayload({
    localTestStreamEnabled: false,
    payload: { trace_id: "", lines: [] }
  });
  assert.strictEqual(out.accept, true);
  assert.strictEqual(out.reason, "test_stream_off");

  out = runtime.shouldAcceptIncomingOverlayPayload({
    localTestStreamEnabled: true,
    payload: { trace_id: "main-test-7", lines: [] }
  });
  assert.strictEqual(out.accept, true);
  assert.strictEqual(out.reason, "local_test_payload");

  out = runtime.shouldAcceptIncomingOverlayPayload({
    localTestStreamEnabled: true,
    payload: { trace_id: "", lines: [], boxes: { mic: { lines: [] }, desktop: { lines: [] } } }
  });
  assert.strictEqual(out.accept, false);
  assert.strictEqual(out.reason, "empty_while_test_stream_on");

  out = runtime.shouldAcceptIncomingOverlayPayload({
    localTestStreamEnabled: true,
    payload: { trace_id: "external-1", lines: ["hello"] }
  });
  assert.strictEqual(out.accept, false);
  assert.strictEqual(out.reason, "non_test_payload_while_test_stream_on");
}

function testAlternatingPayload() {
  const sent = [];
  let timerFn = null;
  const inst = runtime.createLocalTestStreamRuntime({
    normalizeOverlayPayload: (v) => v,
    setIntervalFn: (fn) => {
      timerFn = fn;
      return 99;
    },
    clearIntervalFn: () => {},
    onPayload: (payload) => sent.push(payload),
    onStateChange: () => {},
    linesLimit: 3
  });

  assert.strictEqual(inst.isEnabled(), false);
  inst.setEnabled(true);
  assert.strictEqual(inst.isEnabled(), true);
  assert.ok(typeof timerFn === "function");

  timerFn(); // 1 -> mic
  timerFn(); // 2 -> desktop
  timerFn(); // 3 -> mic

  assert.strictEqual(sent.length, 3);
  assert.strictEqual(sent[0].trace_id, "main-test-1");
  assert.deepStrictEqual(sent[0].boxes.mic.lines, ["test segment 1"]);
  assert.deepStrictEqual(sent[0].boxes.desktop.lines, []);
  assert.deepStrictEqual(sent[1].boxes.desktop.lines, ["test segment 2"]);
  assert.deepStrictEqual(sent[2].boxes.mic.lines, ["test segment 1 test segment 3"]);

  assert.strictEqual(sent[2].boxes.mic.header, "");
  assert.strictEqual(sent[2].boxes.desktop.header, "");
  assert.deepStrictEqual(sent[2].lines, ["test segment 1 test segment 3", "test segment 2"]);
}

function testLinesLimitRetention() {
  const sent = [];
  let timerFn = null;
  const inst = runtime.createLocalTestStreamRuntime({
    normalizeOverlayPayload: (v) => v,
    setIntervalFn: (fn) => {
      timerFn = fn;
      return 1;
    },
    clearIntervalFn: () => {},
    onPayload: (payload) => sent.push(payload),
    onStateChange: () => {},
    linesLimit: 2
  });
  inst.setConstraints({ box: "mic", linesLimit: 2, maxChars: 280, maxSegments: 10, maxLineChars: 31 });
  inst.setConstraints({ box: "desktop", linesLimit: 2, maxChars: 280, maxSegments: 10, maxLineChars: 31 });
  inst.setEnabled(true);
  for (let i = 0; i < 6; i += 1) timerFn();

  const last = sent[sent.length - 1];
  assert.ok(last.boxes.mic.lines.length <= 2);
  assert.ok(last.boxes.desktop.lines.length <= 2);
  assert.ok(last.boxes.mic.text.includes("test segment 5"));
  assert.ok(last.boxes.desktop.text.includes("test segment 6"));
  assert.ok(Array.isArray(last.lines));
}

function testRuntimeConstraintUpdates() {
  const sent = [];
  let timerFn = null;
  const inst = runtime.createLocalTestStreamRuntime({
    normalizeOverlayPayload: (v) => v,
    setIntervalFn: (fn) => {
      timerFn = fn;
      return 11;
    },
    clearIntervalFn: () => {},
    onPayload: (payload) => sent.push(payload),
    onStateChange: () => {},
    linesLimit: 3,
    maxChars: 280
  });
  inst.setConstraints({ linesLimit: 6, maxChars: 280 });
  inst.setEnabled(true);
  for (let i = 0; i < 8; i += 1) timerFn();
  let last = sent[sent.length - 1];
  assert.ok(last.boxes.mic.lines.length >= 1);
  assert.ok(last.boxes.desktop.lines.length >= 1);
  assert.ok(last.boxes.mic.lines.length <= 6);
  assert.ok(last.boxes.desktop.lines.length <= 6);

  inst.setConstraints({ linesLimit: 2, maxChars: 30, maxLineChars: 15 });
  timerFn();
  last = sent[sent.length - 1];
  assert.ok(last.boxes.mic.lines.length <= 2);
  assert.ok(last.boxes.desktop.lines.length <= 2);
  assert.ok(last.boxes.mic.lines.every((line) => String(line || "").length <= 15));
  assert.ok(last.boxes.desktop.lines.every((line) => String(line || "").length <= 15));
}

function testPerBoxConstraintsAndDisable() {
  const sent = [];
  let timerFn = null;
  const inst = runtime.createLocalTestStreamRuntime({
    normalizeOverlayPayload: (v) => v,
    setIntervalFn: (fn) => {
      timerFn = fn;
      return 12;
    },
    clearIntervalFn: () => {},
    onPayload: (payload) => sent.push(payload),
    onStateChange: () => {},
    linesLimit: 3,
    maxChars: 280
  });

  inst.setConstraints({ box: "mic", linesLimit: 6, maxChars: 280 });
  inst.setConstraints({ box: "desktop", linesLimit: 2, maxChars: 280 });
  inst.setEnabled(true, "mic");
  inst.setEnabled(true, "desktop");
  for (let i = 0; i < 14; i += 1) timerFn();
  let last = sent[sent.length - 1];
  assert.ok(last.boxes.mic.lines.length <= 6);
  assert.ok(last.boxes.desktop.lines.length <= 2);

  inst.setEnabled(false, "desktop");
  for (let i = 0; i < 4; i += 1) timerFn();
  last = sent[sent.length - 1];
  assert.ok(last.boxes.desktop.lines.length <= 1);
  assert.ok(last.boxes.mic.lines.length >= 1);
}

function testPerLaneGeometryIsolationInState() {
  let timerFn = null;
  const inst = runtime.createLocalTestStreamRuntime({
    normalizeOverlayPayload: (v) => v,
    setIntervalFn: (fn) => {
      timerFn = fn;
      return 18;
    },
    clearIntervalFn: () => {},
    onPayload: () => {},
    onStateChange: () => {},
    linesLimit: 3,
    maxChars: 280
  });

  inst.setConstraints({ box: "mic", widthPx: 870, paddingPx: 6, fontUi: 5.9, maxSegments: 7, linesLimit: 7 });
  inst.setConstraints({ box: "desktop", widthPx: 510, paddingPx: 6, fontUi: 11.15, maxSegments: 3, linesLimit: 3 });
  inst.setEnabled(true, "mic");
  inst.setEnabled(true, "desktop");
  timerFn();

  const st = inst.getState();
  assert.strictEqual(st.constraints.mic.widthPx, 870);
  assert.strictEqual(st.constraints.desktop.widthPx, 510);
  assert.strictEqual(st.constraints.mic.fontUi, 5.9);
  assert.strictEqual(st.constraints.desktop.fontUi, 11.15);
  assert.strictEqual(st.constraints.mic.segmentLimit, 7);
  assert.strictEqual(st.constraints.desktop.segmentLimit, 3);
}

function testPerBoxSegmentWindowLimit() {
  const sent = [];
  let timerFn = null;
  const inst = runtime.createLocalTestStreamRuntime({
    normalizeOverlayPayload: (v) => v,
    setIntervalFn: (fn) => {
      timerFn = fn;
      return 13;
    },
    clearIntervalFn: () => {},
    onPayload: (payload) => sent.push(payload),
    onStateChange: () => {},
    linesLimit: 3,
    maxChars: 280
  });

  inst.setEnabled(true, "mic");
  inst.setEnabled(true, "desktop");
  for (let i = 0; i < 16; i += 1) timerFn();

  const last = sent[sent.length - 1];
  const micSegments = (last.boxes.mic.text.match(/\btest segment\s+\d+\b/g) || []).length;
  const desktopSegments = (last.boxes.desktop.text.match(/\btest segment\s+\d+\b/g) || []).length;
  assert.ok(/\btest segment\s+13\b/.test(last.boxes.mic.text));
  assert.ok(/\btest segment\s+15\b/.test(last.boxes.mic.text));
  assert.ok(micSegments >= 2);

  assert.ok(/\btest segment\s+14\b/.test(last.boxes.desktop.text));
  assert.ok(/\btest segment\s+16\b/.test(last.boxes.desktop.text));
  assert.ok(desktopSegments >= 2);
}

function testStopToggleHaltsFurtherPayloadEmission() {
  const sent = [];
  let timerFn = null;
  const inst = runtime.createLocalTestStreamRuntime({
    normalizeOverlayPayload: (v) => v,
    setIntervalFn: (fn) => {
      timerFn = fn;
      return 14;
    },
    clearIntervalFn: () => {},
    onPayload: (payload) => sent.push(payload),
    onStateChange: () => {},
    linesLimit: 3,
    maxChars: 280
  });

  inst.setEnabled(true);
  timerFn();
  timerFn();
  const beforeStopCount = sent.length;
  inst.setEnabled(false);
  inst.tick();
  assert.strictEqual(sent.length, beforeStopCount);
}

function testConstraintChangesApplyWithoutRestart() {
  const sent = [];
  let timerFn = null;
  const inst = runtime.createLocalTestStreamRuntime({
    normalizeOverlayPayload: (v) => v,
    setIntervalFn: (fn) => {
      timerFn = fn;
      return 15;
    },
    clearIntervalFn: () => {},
    onPayload: (payload) => sent.push(payload),
    onStateChange: () => {},
    linesLimit: 3,
    maxChars: 280
  });

  inst.setEnabled(true, "mic");
  for (let i = 0; i < 8; i += 1) timerFn();
  inst.setConstraints({ box: "mic", linesLimit: 6, maxChars: 1200 });
  for (let i = 0; i < 4; i += 1) timerFn();
  const last = sent[sent.length - 1];
  assert.ok(last.boxes.mic.text.includes("test segment"));
  assert.strictEqual(last.boxes.desktop.text, "");
  const state = inst.getState();
  assert.strictEqual(state.constraints.mic.linesLimit, 6);
  assert.strictEqual(state.constraints.mic.maxChars, 1200);
}

function testToggleLaneWhileTicking() {
  const sent = [];
  let timerFn = null;
  const inst = runtime.createLocalTestStreamRuntime({
    normalizeOverlayPayload: (v) => v,
    setIntervalFn: (fn) => {
      timerFn = fn;
      return 17;
    },
    clearIntervalFn: () => {},
    onPayload: (payload) => sent.push(payload),
    onStateChange: () => {},
    linesLimit: 3,
    maxChars: 280
  });

  inst.setEnabled(true, "mic");
  inst.setEnabled(true, "desktop");
  for (let i = 0; i < 4; i += 1) timerFn();

  const beforeDisable = sent[sent.length - 1];
  const desktopBefore = String(beforeDisable.boxes.desktop.text || "");
  assert.ok(desktopBefore.includes("test segment 2"));
  assert.ok(desktopBefore.includes("test segment 4"));

  inst.setEnabled(false, "desktop");
  timerFn();
  timerFn();
  const whileDisabled = sent[sent.length - 1];
  assert.strictEqual(String(whileDisabled.boxes.desktop.text || ""), "");

  inst.setEnabled(true, "desktop");
  timerFn();
  timerFn();
  const afterReenable = sent[sent.length - 1];
  assert.ok(String(afterReenable.boxes.desktop.text || "").includes("test segment 8"));
}

function testPayloadCarriesPerBoxGeometry() {
  const sent = [];
  let timerFn = null;
  const inst = runtime.createLocalTestStreamRuntime({
    normalizeOverlayPayload: (v) => v,
    setIntervalFn: (fn) => {
      timerFn = fn;
      return 16;
    },
    clearIntervalFn: () => {},
    onPayload: (payload) => sent.push(payload),
    onStateChange: () => {},
    linesLimit: 3,
    maxChars: 280
  });

  inst.setConstraints({ box: "mic", widthPx: 870, paddingPx: 4, fontUi: 5.9 });
  inst.setConstraints({ box: "desktop", widthPx: 560, paddingPx: 4, fontUi: 3.8 });
  inst.setEnabled(true, "mic");
  inst.setEnabled(true, "desktop");
  timerFn();

  const last = sent[sent.length - 1];
  assert.ok(last);
  assert.strictEqual(last.boxes.mic.width, "870");
  assert.strictEqual(last.boxes.mic.padding, "4");
  assert.strictEqual(last.boxes.mic.fontSize, "5.9");
  assert.strictEqual(last.boxes.desktop.width, "560");
  assert.strictEqual(last.boxes.desktop.padding, "4");
  assert.strictEqual(last.boxes.desktop.fontSize, "3.8");
}

testAcceptancePolicy();
testAlternatingPayload();
testLinesLimitRetention();
testRuntimeConstraintUpdates();
testPerBoxConstraintsAndDisable();
testPerLaneGeometryIsolationInState();
testPerBoxSegmentWindowLimit();
testStopToggleHaltsFurtherPayloadEmission();
testConstraintChangesApplyWithoutRestart();
testToggleLaneWhileTicking();
testPayloadCarriesPerBoxGeometry();
console.log("main_overlay_test_stream_runtime.test.js: ok");
