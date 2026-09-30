const assert = require("assert");
const runtime = require("../lib/line_freeze_compositor");

function testSealedLinesStayStableWhileActiveGrows() {
  const c = runtime.createLineFreezeCompositor({
    maxLines: 3,
    maxChars: 280,
    noWordSplit: true,
    maxLineChars: 15,
  });

  c.appendSegment("test segment 1");
  c.appendSegment("test segment 3");
  const before = c.getState();
  assert.deepStrictEqual(before.sealedLines, ["test segment 1"]);
  assert.strictEqual(before.activeLine, "test segment 3");

  c.appendSegment("test segment 5");
  const after = c.getState();
  assert.deepStrictEqual(after.sealedLines, ["test segment 1", "test segment 3"]);
  assert.strictEqual(after.activeLine, "test segment 5");
}

function testRolloverEvictsWholeOldestLine() {
  const c = runtime.createLineFreezeCompositor({
    maxLines: 3,
    maxChars: 280,
    noWordSplit: true,
    maxLineChars: 15,
  });

  c.appendSegment("test segment 1");
  c.appendSegment("test segment 3");
  c.appendSegment("test segment 5");
  c.appendSegment("test segment 7");
  const s = c.getState();
  assert.deepStrictEqual(s.lines, [
    "test segment 3",
    "test segment 5",
    "test segment 7",
  ]);
}

function testNoWordSplitPreservesWholeWords() {
  const c = runtime.createLineFreezeCompositor({
    maxLines: 4,
    maxChars: 280,
    noWordSplit: true,
    maxLineChars: 19, // forces line boundary near word edge
  });

  c.appendSegment("alpha beta gamma");
  const s = c.getState();
  assert.ok(s.lines.every((line) => !/\s{2,}/.test(line)));
  assert.strictEqual(s.lines.join(" "), "alpha beta gamma");
}

function testLiveConstraintUpdateAppliesImmediately() {
  const c = runtime.createLineFreezeCompositor({
    maxLines: 6,
    maxChars: 280,
    noWordSplit: true,
    maxLineChars: 40,
  });

  c.appendSegment("test segment 1");
  c.appendSegment("test segment 3");
  c.appendSegment("test segment 5");
  c.appendSegment("test segment 7");
  let s = c.getState();
  assert.ok(s.lines.length >= 2);

  s = c.setConstraints({ maxLines: 2, maxChars: 60, maxLineChars: 20 });
  assert.ok(s.lines.length <= 2);
  assert.ok(s.totalChars <= 60);
}

function testDefaultWrappingIsWordAtomicNotSegmentAtomic() {
  const c = runtime.createLineFreezeCompositor({
    maxLines: 3,
    maxChars: 280,
    noWordSplit: true,
    maxLineChars: 32,
  });

  c.appendSegment("test segment 1");
  c.appendSegment("test segment 3");
  const s = c.getState();
  assert.ok(
    s.lines.some((line) => line.includes("test segment 1 test segment 3")),
    "Expected adjacent segments to share a line when words fit."
  );
}

function testCharBudgetEvictsSealedLinesBeforeChangingActiveLine() {
  const c = runtime.createLineFreezeCompositor({
    maxLines: 4,
    maxChars: 32,
    noWordSplit: true,
    maxLineChars: 12,
  });

  c.appendSegment("alpha beta");
  c.appendSegment("gamma delta");
  c.appendSegment("epsilon zeta");
  const before = c.getState();
  const activeBefore = before.activeLine;
  assert.ok(activeBefore.length > 0);

  c.appendSegment("eta theta");
  const after = c.getState();
  assert.strictEqual(
    after.activeLine,
    "eta theta",
    "Active line should be the latest line after seal/append."
  );
  assert.ok(after.sealedLines.length <= before.sealedLines.length);
}

function testNoLeadingOrTrailingSpacesInComposedLines() {
  const c = runtime.createLineFreezeCompositor({
    maxLines: 3,
    maxChars: 280,
    noWordSplit: true,
    maxLineChars: 18,
  });

  c.appendSegment(" one   two ");
  c.appendSegment(" three ");
  c.appendSegment("four");
  const s = c.getState();
  s.lines.forEach((line) => {
    assert.strictEqual(line, line.trim());
    assert.ok(!/\s{2,}/.test(line));
  });
}

function testLineRepresentativeCountingTreatsSameSegmentAsOnePerLine() {
  const c = runtime.createLineFreezeCompositor({
    maxLines: 3,
    maxChars: 280,
    maxSegments: 2,
    noWordSplit: true,
    maxLineChars: 80,
  });
  c.appendSegment("alpha beta gamma", { segmentId: "s1" });
  const s = c.getState();
  assert.strictEqual(s.visibleRepresentatives, 1);
}

function testSplitSegmentCountsOnEachLineItTouches() {
  const c = runtime.createLineFreezeCompositor({
    maxLines: 5,
    maxChars: 280,
    maxSegments: 10,
    noWordSplit: true,
    maxLineChars: 12,
  });
  c.appendSegment("one two three four", { segmentId: "s1" });
  const s = c.getState();
  // same segment split across lines should count once per touched line
  assert.ok(s.lines.length >= 2);
  assert.strictEqual(s.visibleRepresentatives, s.lines.length);
}

function testSegmentBudgetOverflowInSingleActiveLineKeepsNewestRepresentatives() {
  const c = runtime.createLineFreezeCompositor({
    maxLines: 3,
    maxChars: 280,
    maxSegments: 3,
    noWordSplit: true,
    maxLineChars: 130, // keep all tokens on one active line
  });
  c.appendSegment("test segment 1", { segmentId: "s1" });
  c.appendSegment("test segment 3", { segmentId: "s3" });
  c.appendSegment("test segment 5", { segmentId: "s5" });
  c.appendSegment("test segment 7", { segmentId: "s7" });
  const s = c.getState();
  assert.strictEqual(s.visibleRepresentatives, 3);
  assert.ok(s.activeLine.includes("test segment 3"));
  assert.ok(s.activeLine.includes("test segment 5"));
  assert.ok(s.activeLine.includes("test segment 7"));
  assert.ok(!s.activeLine.includes("test segment 1"));
}

function testSegmentBudgetOverflowNeverDropsAllVisibleContent() {
  const c = runtime.createLineFreezeCompositor({
    maxLines: 3,
    maxChars: 280,
    maxSegments: 3,
    noWordSplit: true,
    maxLineChars: 130,
  });
  c.appendSegment("test segment 1");
  c.appendSegment("test segment 3");
  c.appendSegment("test segment 5");
  c.appendSegment("test segment 7");
  const afterSeven = c.getState();
  assert.ok(afterSeven.lines.length > 0);
  c.appendSegment("test segment 9");
  const afterNine = c.getState();
  assert.ok(afterNine.lines.length > 0);
}

function testSegmentBudgetUsesRepresentativesNotUniqueIds() {
  const c = runtime.createLineFreezeCompositor({
    maxLines: 5,
    maxChars: 280,
    maxSegments: 2,
    noWordSplit: true,
    maxLineChars: 12,
  });
  c.appendSegment("one two three four", { segmentId: "s1" }); // splits across lines, 2+ representatives
  c.appendSegment("five six", { segmentId: "s2" });
  const s = c.getState();
  assert.ok(
    s.visibleRepresentatives <= 2,
    `expected representatives<=2, got reps=${s.visibleRepresentatives} unique=${s.uniqueVisibleSegments} lines=${JSON.stringify(s.lines)}`
  );
}

function testPixelFitKeepsWordAtomicAtTs7Boundary() {
  const c = runtime.createLineFreezeCompositor({
    maxLines: 7,
    maxChars: 280,
    maxSegments: 7,
    noWordSplit: true,
    usePixelFit: true,
    maxLinePx: 778,
    fontUi: 5.9,
    maxLineChars: 58,
  });

  c.appendSegment("test segment 1");
  c.appendSegment("test segment 3");
  c.appendSegment("test segment 5");
  c.appendSegment("test segment 7");
  const s = c.getState();
  const joined = s.lines.join("\n");
  assert.ok(joined.includes("test segment 1 test segment 3"));
  assert.ok(joined.includes("test segment"), `joined=${joined}`);
  assert.ok(!joined.includes("\nsegment\n7"), `joined=${joined}`);
}

function testPixelFitDoesNotEarlyWrapFromLegacyCharBudget() {
  const c = runtime.createLineFreezeCompositor({
    maxLines: 7,
    maxChars: 280,
    maxSegments: 7,
    noWordSplit: true,
    usePixelFit: true,
    maxLinePx: 778,
    fontUi: 5.9,
    // Intentionally too small if interpreted as a hard cap; pixel fit should
    // still allow normal line fill based on measured width.
    maxLineChars: 31,
  });

  c.appendSegment("test segment 1");
  c.appendSegment("test segment 3");
  c.appendSegment("test segment 5");
  c.appendSegment("test segment 7");
  c.appendSegment("test segment 9");
  c.appendSegment("test segment 11");
  const joined = c.getState().lines.join("\n");
  assert.ok(!joined.includes("\nsegment 9\ntest segment 11"), `joined=${joined}`);
}

testSealedLinesStayStableWhileActiveGrows();
testRolloverEvictsWholeOldestLine();
testNoWordSplitPreservesWholeWords();
testLiveConstraintUpdateAppliesImmediately();
testDefaultWrappingIsWordAtomicNotSegmentAtomic();
testCharBudgetEvictsSealedLinesBeforeChangingActiveLine();
testNoLeadingOrTrailingSpacesInComposedLines();
testLineRepresentativeCountingTreatsSameSegmentAsOnePerLine();
testSplitSegmentCountsOnEachLineItTouches();
testSegmentBudgetOverflowInSingleActiveLineKeepsNewestRepresentatives();
testSegmentBudgetOverflowNeverDropsAllVisibleContent();
testSegmentBudgetUsesRepresentativesNotUniqueIds();
testPixelFitKeepsWordAtomicAtTs7Boundary();
testPixelFitDoesNotEarlyWrapFromLegacyCharBudget();
console.log("line_freeze_compositor.test.js: ok");
