const assert = require("assert");
const authority = require("../lib/overlay_constraints_authority");

function testNormalizeLaneConstraintClampsValues() {
  const out = authority.normalizeLaneConstraint({
    maxSegments: 999,
    maxChars: 1,
    widthPx: 50,
    paddingPx: -3,
    fontUi: 0,
    noWordSplit: false,
  });
  assert.strictEqual(out.linesLimit, 10);
  assert.strictEqual(out.maxSegments, 40);
  assert.strictEqual(out.maxChars, 20);
  assert.strictEqual(out.widthPx, 100);
  assert.strictEqual(out.paddingPx, 0);
  assert.strictEqual(out.fontUi, 0.1);
  assert.strictEqual(out.noWordSplit, false);
}

function testBuildSetTestStreamPayloadUsesDefaults() {
  const out = authority.buildSetTestStreamPayload({
    enabled: true,
    box: "mic",
    cfg: {},
  });
  assert.deepStrictEqual(out, {
    enabled: true,
    box: "mic",
    linesLimit: 3,
    maxChars: 280,
    maxSegments: 3,
    widthPx: 640,
    paddingPx: 6,
    fontUi: 3,
    noWordSplit: true,
  });
}

function testBuildSetTestStreamPayloadsPerBox() {
  const out = authority.buildSetTestStreamPayloads({
    enabled: true,
    boxes: {
      mic: {
        maxSegments: 7,
        maxChars: 600,
        widthPx: 870,
        paddingPx: 4,
        fontUi: 5.9,
        noWordSplit: true,
      },
      desktop: {
        maxSegments: 3,
        maxChars: 280,
        widthPx: 510,
        paddingPx: 4,
        fontUi: 11.15,
        noWordSplit: true,
      },
    },
  });

  assert.strictEqual(out.length, 2);
  assert.deepStrictEqual(out[0], {
    enabled: true,
    box: "mic",
    linesLimit: 7,
    maxChars: 600,
    maxSegments: 7,
    widthPx: 870,
    paddingPx: 4,
    fontUi: 5.9,
    noWordSplit: true,
  });
  assert.deepStrictEqual(out[1], {
    enabled: true,
    box: "desktop",
    linesLimit: 3,
    maxChars: 280,
    maxSegments: 3,
    widthPx: 510,
    paddingPx: 4,
    fontUi: 11.15,
    noWordSplit: true,
  });
}

function testBuildConstraintPatchCapturesNumericAndNoWordSplit() {
  const out = authority.buildConstraintPatch({
    box: "DESKTOP",
    linesLimit: "6",
    maxChars: "280",
    maxSegments: "9",
    widthPx: "510",
    paddingPx: "6",
    fontUi: "11.15",
    maxLineChars: "31",
    noWordSplit: false,
  });
  assert.strictEqual(out.hasConstraintPatch, true);
  assert.deepStrictEqual(out.patch, {
    box: "desktop",
    linesLimit: 6,
    maxChars: 280,
    maxSegments: 9,
    widthPx: 510,
    paddingPx: 6,
    fontUi: 11.15,
    maxLineChars: 31,
    noWordSplit: false,
  });
}

function testBuildConstraintPatchKeepsAuthorityTrace() {
  const out = authority.buildConstraintPatch({
    box: "mic",
    authorityTrace: {
      widthPx: "incoming",
      maxLineChars: "derived",
      preferFallbackGeometry: true,
    },
  });
  assert.strictEqual(out.hasConstraintPatch, true);
  assert.deepStrictEqual(out.patch, {
    box: "mic",
    noWordSplit: true,
    authorityTrace: {
      widthPx: "incoming",
      maxLineChars: "derived",
      preferFallbackGeometry: true,
    },
  });
}

function testBuildConstraintPatchIgnoresEmptyNumericFields() {
  const out = authority.buildConstraintPatch({
    box: "mic",
    linesLimit: "",
    maxChars: "",
    maxSegments: "",
    widthPx: "",
    paddingPx: "",
    fontUi: "",
    maxLineChars: "",
  });
  assert.strictEqual(out.hasConstraintPatch, false);
  assert.deepStrictEqual(out.patch, {
    box: "mic",
    noWordSplit: true,
  });
}

function testMergeRuntimeLaneConstraintPrefersIncomingWhenFallbackMissing() {
  const out = authority.mergeRuntimeLaneConstraint({
    incoming: {
      linesLimit: 3,
      maxChars: 280,
      maxSegments: 3,
      widthPx: 870,
      paddingPx: 6,
      fontUi: 5.9,
      maxLineChars: 46,
      noWordSplit: true,
    },
    fallback: {
      widthPx: null,
      paddingPx: null,
      fontUi: null,
    },
    debugRaw: {
      width: "",
      font: "",
      padding: "",
    },
  });
  assert.strictEqual(out.linesLimit, 3);
  assert.strictEqual(out.maxChars, 280);
  assert.strictEqual(out.maxSegments, 3);
  assert.strictEqual(out.widthPx, 870);
  assert.strictEqual(out.paddingPx, 6);
  assert.strictEqual(out.fontUi, 5.9);
  assert.strictEqual(Number.isFinite(Number(out.maxLineChars)), false);
  assert.ok(out.authorityTrace);
  assert.strictEqual(out.authorityTrace.preferFallbackGeometry, true);
  assert.strictEqual(out.authorityTrace.widthPx, "incoming");
  assert.strictEqual(out.authorityTrace.fontUi, "incoming");
  assert.strictEqual(out.authorityTrace.maxLineChars, "derived");
}

testNormalizeLaneConstraintClampsValues();
testBuildSetTestStreamPayloadUsesDefaults();
testBuildSetTestStreamPayloadsPerBox();
testBuildConstraintPatchCapturesNumericAndNoWordSplit();
testBuildConstraintPatchKeepsAuthorityTrace();
testBuildConstraintPatchIgnoresEmptyNumericFields();
testMergeRuntimeLaneConstraintPrefersIncomingWhenFallbackMissing();
