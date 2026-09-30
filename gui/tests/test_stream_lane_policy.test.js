const assert = require("assert");
const lanePolicy = require("../lib/test_stream_lane_policy");

function testWordAtomicDefaultAcrossSegments() {
  const p = lanePolicy.createTestStreamLanePolicy({ linesLimit: 3, maxChars: 280 });
  p.setEnabled(true, "mic");
  p.append("mic", "test segment 1");
  p.append("mic", "test segment 3");
  const lines = p.laneLines("mic");
  assert.ok(lines.some((line) => line.includes("test segment 1 test segment 3")));
}

function testPerLaneIsolation() {
  const p = lanePolicy.createTestStreamLanePolicy({ linesLimit: 2, maxChars: 280 });
  p.setEnabled(true, "mic");
  p.setEnabled(true, "desktop");
  p.setConstraints({ box: "mic", linesLimit: 2, maxChars: 280, maxSegments: 10 });
  p.setConstraints({ box: "desktop", linesLimit: 2, maxChars: 280, maxSegments: 10 });

  p.append("mic", "test segment 1");
  p.append("desktop", "test segment 2");
  p.append("mic", "test segment 3");
  p.append("desktop", "test segment 4");
  p.append("mic", "test segment 5");

  const st = p.getState();
  assert.ok(st.mic.segmentWindow.includes("test segment 5"));
  assert.ok(st.desktop.segmentWindow.includes("test segment 4"));
  assert.ok(st.mic.lines.join(" ").includes("test segment 5"));
  assert.ok(st.desktop.lines.join(" ").includes("test segment 4"));
}

function testConstraintUpdatesApplyImmediately() {
  const p = lanePolicy.createTestStreamLanePolicy({ linesLimit: 2, maxChars: 280 });
  p.setEnabled(true, "mic");
  p.append("mic", "test segment 1");
  p.append("mic", "test segment 3");

  p.setConstraints({ box: "mic", linesLimit: 6, maxChars: 1200, maxSegments: 10 });
  const c = p.laneConstraints("mic");
  assert.strictEqual(c.linesLimit, 6);
  assert.strictEqual(c.maxChars, 1200);

  p.append("mic", "test segment 5");
  const lines = p.laneLines("mic");
  assert.ok(lines.join(" ").includes("test segment 5"));
}

function testAuthorityTraceIsStoredPerLane() {
  const p = lanePolicy.createTestStreamLanePolicy({ linesLimit: 2, maxChars: 280 });
  p.setEnabled(true, "mic");
  p.setConstraints({
    box: "mic",
    linesLimit: 3,
    maxChars: 280,
    authorityTrace: {
      widthPx: "incoming",
      maxLineChars: "derived",
      preferFallbackGeometry: true,
    },
  });
  const c = p.laneConstraints("mic");
  assert.ok(c.authorityTrace);
  assert.strictEqual(c.authorityTrace.widthPx, "incoming");
  assert.strictEqual(c.authorityTrace.maxLineChars, "derived");
}

function testGeometryDrivenLineBudgetNotCappedByMaxChars() {
  const p = lanePolicy.createTestStreamLanePolicy({ linesLimit: 3, maxChars: 280 });
  p.setEnabled(true, "mic");
  p.setConstraints({
    box: "mic",
    linesLimit: 3,
    maxChars: 280,
    widthPx: 1200,
    paddingPx: 6,
    fontUi: 3,
  });
  const c = p.laneConstraints("mic");
  // Geometry is authoritative for per-line wrapping.
  assert.ok(c.maxLineChars > 100, `unexpected budget ${c.maxLineChars}`);
}

function testSoftSegmentLimitAppliesOnWrapBoundary() {
  const p = lanePolicy.createTestStreamLanePolicy({
    linesLimit: 3,
    maxChars: 280,
    deriveMaxLineChars: () => 18,
  });
  p.setEnabled(true, "mic");
  p.setConstraints({ box: "mic", linesLimit: 3, maxChars: 280, maxSegments: 3, maxLineChars: 15 });

  p.append("mic", "test segment 1");
  p.append("mic", "test segment 3");
  p.append("mic", "test segment 5");
  p.append("mic", "test segment 7");
  p.append("mic", "test segment 9");

  const st = p.getState().mic;
  const visible = st.lines.join(" ");
  assert.ok(/\bsegment 9\b/.test(visible));
  assert.ok(!/\bsegment 1\b/.test(visible), `visible=${visible}`);
}

function testSegmentLimitEnforcedWhenAllSegmentsFitSingleLine() {
  const p = lanePolicy.createTestStreamLanePolicy({
    linesLimit: 3,
    maxChars: 280,
    // Intentionally huge so compositor would otherwise keep everything active.
    deriveMaxLineChars: () => 240,
  });
  p.setEnabled(true, "mic");
  p.setConstraints({ box: "mic", linesLimit: 3, maxChars: 280, maxSegments: 3, maxLineChars: 15 });

  p.append("mic", "test segment 1");
  p.append("mic", "test segment 3");
  p.append("mic", "test segment 5");
  p.append("mic", "test segment 7");
  p.append("mic", "test segment 9");

  const st = p.getState().mic;
  const visible = st.lines.join(" ");
  // Representative budget is line-based. In a single-line layout, overflow
  // may evict the whole line and retain only newest content.
  assert.ok(!/\bsegment 1\b/.test(visible), `visible=${visible}`);
  assert.ok(/\bsegment 9\b/.test(visible));
}

function testSingleLineOverflowDoesNotSlideExistingContent() {
  const p = lanePolicy.createTestStreamLanePolicy({
    linesLimit: 3,
    maxChars: 280,
    deriveMaxLineChars: () => 15,
  });
  p.setEnabled(true, "mic");
  p.setConstraints({ box: "mic", linesLimit: 3, maxChars: 280, maxSegments: 3, maxLineChars: 15 });

  p.append("mic", "test segment 1");
  p.append("mic", "test segment 3");
  p.append("mic", "test segment 5");
  const beforeLines = p.laneLines("mic");
  const beforeJoined = beforeLines.join(" | ");
  assert.ok(beforeJoined.includes("test segment 1"), `before=${beforeJoined}`);
  assert.ok(beforeJoined.includes("test segment 3"), `before=${beforeJoined}`);
  assert.ok(beforeJoined.includes("test segment 5"), `before=${beforeJoined}`);

  p.append("mic", "test segment 7");
  const afterJoined = p.laneLines("mic").join(" | ");
  // Representative budget is authoritative without retroactive rebuild/slide.
  assert.ok(!afterJoined.includes("test segment 1"), `after=${afterJoined}`);
  assert.ok(afterJoined.includes("segment 5"), `after=${afterJoined}`);
  assert.ok(afterJoined.includes("segment 7"), `after=${afterJoined}`);
}

function testLineFreezeKeepsInitialSplitWithoutRetroactivePolish() {
  const p = lanePolicy.createTestStreamLanePolicy({
    linesLimit: 3,
    maxChars: 280,
    deriveMaxLineChars: () => 15,
  });
  p.setEnabled(true, "mic");
  p.append("mic", "alpha beta test");
  p.append("mic", "segment 5");

  const lines = p.laneLines("mic");
  assert.ok(lines.length >= 2);
  assert.ok(lines[0].endsWith(" test"));
  assert.ok(/^segment 5$/.test(lines[1]));
}

function testWordSplitStaysWordAtomic() {
  const p = lanePolicy.createTestStreamLanePolicy({
    linesLimit: 3,
    maxChars: 280,
    deriveMaxLineChars: () => 23,
  });
  p.setEnabled(true, "mic");
  p.append("mic", "test segment 11 test segment 13 test segment");
  p.append("mic", "15");

  const lines = p.laneLines("mic");
  assert.ok(lines.length >= 2);
  assert.ok(lines.some((line) => /\b15\b/.test(line)));
  assert.ok(lines.every((line) => !/segm\s*$/.test(line)));
}

function testRolloverDoesNotReformSplitSegmentFromPriorLine() {
  const p = lanePolicy.createTestStreamLanePolicy({
    linesLimit: 3,
    maxChars: 1000,
    deriveMaxLineChars: () => 14,
  });
  p.setEnabled(true, "mic");
  p.setConstraints({
    box: "mic",
    linesLimit: 3,
    maxChars: 1000,
    maxSegments: 20,
    maxLineChars: 14,
  });

  for (let n = 1; n <= 17; n += 2) {
    p.append("mic", `test segment ${n}`);
  }

  const lines = p.laneLines("mic");
  // After rollover, split fragments must stay stable; do not rebuild full segment text
  // in later lines once older lines are evicted.
  assert.ok(lines.includes("segment 17"));
  assert.ok(lines.some((line) => line.includes("15 test")));
  assert.ok(!lines.includes("test segment 17"));
}

function testRepeatedSameConstraintsDoNotRecomposeFragments() {
  const p = lanePolicy.createTestStreamLanePolicy({ linesLimit: 3, maxChars: 1000 });
  p.setEnabled(true, "mic");
  p.setConstraints({
    box: "mic",
    linesLimit: 3,
    maxChars: 1000,
    maxSegments: 20,
    maxLineChars: 14,
  });
  for (let n = 1; n <= 17; n += 2) {
    p.append("mic", `test segment ${n}`);
  }
  const before = p.laneLines("mic");
  p.setConstraints({
    box: "mic",
    linesLimit: 3,
    maxChars: 1000,
    maxSegments: 20,
    maxLineChars: 14,
  });
  const after = p.laneLines("mic");
  assert.deepStrictEqual(after, before);
}

function testSegmentLimitTrimEvictsOldestSealedLine() {
  const p = lanePolicy.createTestStreamLanePolicy({
    linesLimit: 3,
    maxChars: 1000,
    deriveMaxLineChars: () => 15,
  });
  p.setEnabled(true, "mic");
  p.setConstraints({
    box: "mic",
    linesLimit: 3,
    maxChars: 1000,
    maxSegments: 3,
    maxLineChars: 15,
  });

  p.append("mic", "test segment 1");
  p.append("mic", "test segment 3");
  p.append("mic", "test segment 5");
  p.append("mic", "test segment 7");
  const after = p.laneLines("mic").join(" ");

  // On maxSegments overflow, evict oldest segment and retain newest window.
  assert.ok(!/\btest segment 1\b/.test(after));
  assert.ok(/\btest segment 3\b/.test(after));
  assert.ok(/\bsegment 5\b/.test(after));
  assert.ok(/\bsegment 7\b/.test(after));
}

function testSegmentLimitTrimDoesNotCollapseToTrailingFragment() {
  const p = lanePolicy.createTestStreamLanePolicy({
    linesLimit: 3,
    maxChars: 280,
    deriveMaxLineChars: () => 15,
  });
  p.setEnabled(true, "mic");
  p.setEnabled(true, "desktop");
  p.setConstraints({ box: "mic", linesLimit: 3, maxChars: 280, maxSegments: 3, maxLineChars: 15 });
  p.setConstraints({ box: "desktop", linesLimit: 3, maxChars: 280, maxSegments: 3, maxLineChars: 15 });

  for (let n = 1; n <= 8; n += 1) {
    const box = (n % 2 === 1) ? "mic" : "desktop";
    p.append(box, `test segment ${n}`);
  }

  const st = p.getState();
  const mic = st.mic.lines.join(" ");
  const desktop = st.desktop.lines.join(" ");
  // Avoid collapsing to bare trailing fragments while preserving newest window.
  assert.ok(/\btest segment 7\b/.test(mic), `mic=${mic}`);
  assert.ok(!/\btest segment 1\b/.test(mic), `mic=${mic}`);
  assert.ok(/\btest segment 3\b/.test(mic), `mic=${mic}`);
  assert.ok(/\btest segment 8\b/.test(desktop), `desktop=${desktop}`);
  assert.ok(!/\btest segment 2\b/.test(desktop), `desktop=${desktop}`);
  assert.ok(/\btest segment 4\b/.test(desktop), `desktop=${desktop}`);
}

function testSegmentOverflowKeepsNewestVisibleSequence() {
  const p = lanePolicy.createTestStreamLanePolicy({
    linesLimit: 3,
    maxChars: 280,
    deriveMaxLineChars: () => 31,
  });
  p.setEnabled(true, "mic");
  p.setConstraints({ box: "mic", linesLimit: 3, maxChars: 280, maxSegments: 7, maxLineChars: 31 });

  for (let n = 1; n <= 15; n += 2) {
    p.append("mic", `test segment ${n}`);
  }

  const lines = p.laneLines("mic");
  const joined = lines.join(" ");
  assert.ok(!/\btest segment 1\b/.test(joined), `joined=${joined}`);
  assert.ok(!/\btest segment 3\b/.test(joined), `joined=${joined}`);
  assert.ok(/\btest segment 7\b/.test(joined), `joined=${joined}`);
  assert.ok(/\btest segment 9 test segment 11\b/.test(joined), `joined=${joined}`);
  assert.ok(/\btest segment 13 test segment 15\b/.test(joined), `joined=${joined}`);
}

function testNoHardCollapseAtSeq13Transition() {
  const p = lanePolicy.createTestStreamLanePolicy({
    linesLimit: 3,
    maxChars: 280,
    deriveMaxLineChars: () => 90,
  });
  p.setEnabled(true, "mic");
  p.setConstraints({
    box: "mic",
    linesLimit: 3,
    maxChars: 280,
    maxSegments: 3,
    maxLineChars: 90,
  });

  p.append("mic", "test segment 1");
  p.append("mic", "test segment 3");
  p.append("mic", "test segment 5");
  p.append("mic", "test segment 7");
  p.append("mic", "test segment 9");
  p.append("mic", "test segment 11");
  const before = p.laneLines("mic").join("\n");
  assert.ok(before.includes("segment 11"), `before=${before}`);

  p.append("mic", "test segment 13");
  const afterLines = p.laneLines("mic");
  const after = afterLines.join("\n");
  // Regression: do not collapse to only the newest segment when overflow occurs.
  assert.ok(afterLines.length >= 1, `after=${after}`);
  assert.ok(after.includes("segment 11"), `after=${after}`);
  assert.ok(after.includes("segment 13"), `after=${after}`);
}

testWordAtomicDefaultAcrossSegments();
testPerLaneIsolation();
testConstraintUpdatesApplyImmediately();
testAuthorityTraceIsStoredPerLane();
testGeometryDrivenLineBudgetNotCappedByMaxChars();
testSoftSegmentLimitAppliesOnWrapBoundary();
testLineFreezeKeepsInitialSplitWithoutRetroactivePolish();
testWordSplitStaysWordAtomic();
testSegmentLimitEnforcedWhenAllSegmentsFitSingleLine();
testSingleLineOverflowDoesNotSlideExistingContent();
testRolloverDoesNotReformSplitSegmentFromPriorLine();
testRepeatedSameConstraintsDoNotRecomposeFragments();
testSegmentLimitTrimEvictsOldestSealedLine();
testSegmentLimitTrimDoesNotCollapseToTrailingFragment();
testSegmentOverflowKeepsNewestVisibleSequence();
testNoHardCollapseAtSeq13Transition();
console.log("test_stream_lane_policy.test.js: ok");
