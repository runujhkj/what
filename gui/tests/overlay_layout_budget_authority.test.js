const assert = require("assert");
const budget = require("../lib/overlay_layout_budget_authority");

function testDeriveLaneBudgetUsesExplicitMaxLineChars() {
  const out = budget.deriveLaneBudget({
    linesLimit: 7,
    maxChars: 280,
    maxSegments: 7,
    widthPx: 870,
    paddingPx: 6,
    fontUi: 5.9,
    maxLineChars: 55,
  });
  assert.strictEqual(out.linesLimit, 7);
  assert.strictEqual(out.maxSegments, 7);
  assert.strictEqual(out.maxLineChars, 55);
  assert.strictEqual(out.derivation.maxLineChars, "incoming");
}

function testDeriveLaneBudgetComputesDerivedMaxLineChars() {
  const out = budget.deriveLaneBudget({
    linesLimit: 3,
    maxChars: 280,
    maxSegments: 3,
    widthPx: 870,
    paddingPx: 6,
    fontUi: 5.9,
  });
  assert.strictEqual(out.maxLineChars, out.derivation.geometryMaxLineChars);
  assert.strictEqual(out.derivation.maxLineChars, "derived");
  assert.ok(out.maxLineChars > out.derivation.floorMaxLineChars);
  assert.strictEqual(out.derivation.floorMaxLineChars, 31);
}

function testGeometryDrivenEstimateShrinksWithFontSize() {
  const small = budget.deriveMaxLineCharsFromGeometry({
    widthPx: 870,
    paddingPx: 6,
    fontUi: 5.9,
  });
  const large = budget.deriveMaxLineCharsFromGeometry({
    widthPx: 870,
    paddingPx: 6,
    fontUi: 17.95,
  });
  assert.ok(large < small, `expected large(${large}) < small(${small})`);
}

function testGeometryDrivenEstimateMatchesMicDesktopAnchors() {
  const mic = budget.deriveMaxLineCharsFromGeometry({
    widthPx: 790,
    paddingPx: 6,
    fontUi: 5.9,
  });
  const desktop = budget.deriveMaxLineCharsFromGeometry({
    widthPx: 510,
    paddingPx: 6,
    fontUi: 11.15,
  });
  assert.ok(mic >= 52 && mic <= 62, `unexpected mic budget ${mic}`);
  assert.ok(desktop >= 24 && desktop <= 31, `unexpected desktop budget ${desktop}`);
  assert.ok(mic > desktop, `expected mic(${mic}) > desktop(${desktop})`);
}

testDeriveLaneBudgetUsesExplicitMaxLineChars();
testDeriveLaneBudgetComputesDerivedMaxLineChars();
testGeometryDrivenEstimateShrinksWithFontSize();
testGeometryDrivenEstimateMatchesMicDesktopAnchors();
console.log("overlay_layout_budget_authority.test.js: ok");
