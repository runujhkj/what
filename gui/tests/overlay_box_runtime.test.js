const assert = require("assert");
const runtime = require("../lib/overlay_box_runtime");

function testNormalizeLaneConstraint() {
  const out = runtime.normalizeLaneConstraint({
    maxSegments: 7,
    maxChars: 280,
    widthPx: 870,
    paddingPx: 6,
    fontUi: 5.9,
    maxLineChars: 999,
    noWordSplit: true,
  });
  assert.strictEqual(out.linesLimit, 7);
  assert.strictEqual(out.maxSegments, 7);
  assert.strictEqual(out.maxChars, 280);
  assert.strictEqual(out.widthPx, 870);
  assert.strictEqual(out.paddingPx, 6);
  assert.strictEqual(out.fontUi, 5.9);
  assert.strictEqual(out.maxLineChars, 240);
  assert.strictEqual(out.noWordSplit, true);
}

function testMergeRuntimeConstraintsPrefersFallbackGeometry() {
  const merged = runtime.mergeRuntimeConstraints({
    incoming: {
      linesLimit: 3,
      maxSegments: 3,
      maxChars: 280,
      widthPx: 510,
      paddingPx: 6,
      fontUi: 5.9,
      maxLineChars: 46,
      noWordSplit: true,
    },
    fallback: {
      linesLimit: 7,
      maxSegments: 7,
      maxChars: 280,
      widthPx: 870,
      paddingPx: 4,
      fontUi: 11.15,
      noWordSplit: true,
    },
    preferFallbackGeometry: true,
  });
  assert.strictEqual(merged.linesLimit, 3);
  assert.strictEqual(merged.maxSegments, 3);
  assert.strictEqual(merged.widthPx, 510);
  assert.strictEqual(merged.paddingPx, 6);
  assert.strictEqual(merged.fontUi, 5.9);
  assert.strictEqual(Object.prototype.hasOwnProperty.call(merged, "maxLineChars"), false);
}

function testMergeRuntimeConstraintsUsesFallbackGeometryWhenIncomingMissing() {
  const merged = runtime.mergeRuntimeConstraints({
    incoming: {
      linesLimit: 3,
      maxSegments: 3,
      maxChars: 280,
      widthPx: "",
      paddingPx: "",
      fontUi: "",
      noWordSplit: true,
    },
    fallback: {
      widthPx: 870,
      paddingPx: 4,
      fontUi: 11.15,
    },
    preferFallbackGeometry: true,
  });
  assert.strictEqual(merged.widthPx, 870);
  assert.strictEqual(merged.paddingPx, 4);
  assert.strictEqual(merged.fontUi, 11.15);
}

function testShouldPreferFallbackGeometryFromEmptyRawFields() {
  const out = runtime.shouldPreferFallbackGeometry({
    width: "",
    font: "",
    padding: "",
  });
  assert.strictEqual(out, true);
}

function testMergeRuntimeConstraintsDoesNotInjectFallbackDefaults() {
  const merged = runtime.mergeRuntimeConstraints({
    incoming: {
      linesLimit: 7,
      maxSegments: 7,
      maxChars: 280,
      widthPx: 870,
      paddingPx: 6,
      fontUi: 5.9,
      noWordSplit: true,
    },
    fallback: {},
    preferFallbackGeometry: true,
  });
  assert.strictEqual(merged.linesLimit, 7);
  assert.strictEqual(merged.maxSegments, 7);
  assert.strictEqual(merged.maxChars, 280);
  assert.strictEqual(merged.widthPx, 870);
  assert.strictEqual(merged.paddingPx, 6);
  assert.strictEqual(merged.fontUi, 5.9);
}

testNormalizeLaneConstraint();
testMergeRuntimeConstraintsPrefersFallbackGeometry();
testMergeRuntimeConstraintsUsesFallbackGeometryWhenIncomingMissing();
testShouldPreferFallbackGeometryFromEmptyRawFields();
testMergeRuntimeConstraintsDoesNotInjectFallbackDefaults();
console.log("overlay_box_runtime.test.js: ok");
