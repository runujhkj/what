const assert = require("assert");
const lanePipeline = require("../lib/test_stream_lane_pipeline");
const lanePolicyRuntime = require("../lib/test_stream_lane_policy");

function testPickLaneForCounter() {
  assert.strictEqual(lanePipeline.pickLaneForCounter({
    counter: 1,
    boxEnabled: { mic: true, desktop: true }
  }), "mic");
  assert.strictEqual(lanePipeline.pickLaneForCounter({
    counter: 2,
    boxEnabled: { mic: true, desktop: true }
  }), "desktop");
  assert.strictEqual(lanePipeline.pickLaneForCounter({
    counter: 100,
    boxEnabled: { mic: true, desktop: false }
  }), "mic");
}

function testInterleaveLaneLines() {
  const merged = lanePipeline.interleaveLaneLines({
    micLines: ["m1", "m2"],
    desktopLines: ["d1"],
  });
  assert.deepStrictEqual(merged, ["m1", "d1", "m2"]);
}

function testComputeRootLinesLimit() {
  const out = lanePipeline.computeRootLinesLimit({
    micConstraints: { linesLimit: 7 },
    desktopConstraints: { linesLimit: 3 },
    fallbackLimit: 1,
  });
  assert.strictEqual(out, 7);
}

function testBuildTickPayloadWithLanePolicy() {
  const lanePolicy = lanePolicyRuntime.createTestStreamLanePolicy({
    linesLimit: 3,
    maxChars: 280,
  });
  lanePolicy.setEnabled(true, "mic");
  lanePolicy.setEnabled(true, "desktop");
  lanePolicy.setConstraints({ box: "mic", widthPx: 870, paddingPx: 4, fontUi: 5.9, linesLimit: 7, maxSegments: 7 });
  lanePolicy.setConstraints({ box: "desktop", widthPx: 510, paddingPx: 4, fontUi: 11.15, linesLimit: 3, maxSegments: 3 });

  const p1 = lanePipeline.buildTickPayload({
    counter: 1,
    sample: "test segment 1",
    lanePolicy,
    defaultLinesLimit: 3,
    normalizeOverlayPayload: (v) => v,
  });
  assert.deepStrictEqual(p1.boxes.mic.lines, ["test segment 1"]);
  assert.deepStrictEqual(p1.boxes.desktop.lines, []);
  assert.strictEqual(p1.boxes.mic.width, "870");
  assert.strictEqual(p1.boxes.desktop.width, "510");

  const p2 = lanePipeline.buildTickPayload({
    counter: 2,
    sample: "test segment 2",
    lanePolicy,
    defaultLinesLimit: 3,
    normalizeOverlayPayload: (v) => v,
  });
  assert.ok(Array.isArray(p2.boxes.desktop.lines));
  assert.ok(p2.boxes.desktop.lines.join(" ").includes("test segment 2"));
  assert.ok(Array.isArray(p2.lines));
  assert.ok(p2.lines.length <= 7);
}

testPickLaneForCounter();
testInterleaveLaneLines();
testComputeRootLinesLimit();
testBuildTickPayloadWithLanePolicy();
console.log("test_stream_lane_pipeline.test.js: ok");
