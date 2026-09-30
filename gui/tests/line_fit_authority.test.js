const assert = require("node:assert");
const lineFitAuthority = require("../lib/line_fit_authority");

function testDeriveContentBoxUsesGeometryOnly() {
  const out = lineFitAuthority.deriveContentBox({
    widthPx: 740,
    heightPx: 270,
    paddingPx: 6,
    fontUi: 6.4,
  });
  assert.strictEqual(out.widthPx, 740);
  assert.strictEqual(out.heightPx, 270);
  assert.strictEqual(out.paddingPx, 6);
  assert.strictEqual(out.contentWidthPx, 728);
  assert.strictEqual(out.contentHeightPx, 258);
}

function testDeriveContentBoxClampsAtLeastOnePixel() {
  const out = lineFitAuthority.deriveContentBox({
    widthPx: 4,
    heightPx: 4,
    paddingPx: 10,
  });
  assert.strictEqual(out.contentWidthPx, 1);
  assert.strictEqual(out.contentHeightPx, 1);
}

function testCanAppendTokenUsesMeasuredWidthsOnly() {
  const fit = lineFitAuthority.canAppendToken({
    maxLinePx: 728,
    lineWidthPx: 700,
    tokenWidthPx: 20,
    spaceWidthPx: 8,
    lineHasTokens: false,
  });
  assert.strictEqual(fit.fits, true);
  assert.strictEqual(fit.nextWidthPx, 720);

  const noFit = lineFitAuthority.canAppendToken({
    maxLinePx: 728,
    lineWidthPx: 700,
    tokenWidthPx: 20,
    spaceWidthPx: 8,
    lineHasTokens: true,
  });
  assert.strictEqual(noFit.fits, true);
  assert.strictEqual(noFit.nextWidthPx, 728);

  const overflow = lineFitAuthority.canAppendToken({
    maxLinePx: 728,
    lineWidthPx: 701,
    tokenWidthPx: 20,
    spaceWidthPx: 8,
    lineHasTokens: true,
  });
  assert.strictEqual(overflow.fits, false);
  assert.strictEqual(overflow.nextWidthPx, 729);
}

testDeriveContentBoxUsesGeometryOnly();
testDeriveContentBoxClampsAtLeastOnePixel();
testCanAppendTokenUsesMeasuredWidthsOnly();

console.log("line_fit_authority.test.js: ok");

