function clampNumber(value, min, fallback) {
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  return Math.max(min, n);
}

function deriveContentBox(input) {
  const src = input && typeof input === "object" ? input : {};
  const widthPx = clampNumber(src.widthPx, 1, 640);
  const heightPx = clampNumber(src.heightPx, 1, 140);
  const paddingPx = clampNumber(src.paddingPx, 0, 6);
  const contentWidthPx = Math.max(1, widthPx - (paddingPx * 2));
  const contentHeightPx = Math.max(1, heightPx - (paddingPx * 2));
  return {
    widthPx,
    heightPx,
    paddingPx,
    contentWidthPx,
    contentHeightPx,
  };
}

function canAppendToken(input) {
  const src = input && typeof input === "object" ? input : {};
  const maxLinePx = clampNumber(src.maxLinePx, 1, 640);
  const lineWidthPx = clampNumber(src.lineWidthPx, 0, 0);
  const tokenWidthPx = clampNumber(src.tokenWidthPx, 0, 0);
  const spaceWidthPx = clampNumber(src.spaceWidthPx, 0, 0);
  const lineHasTokens = src.lineHasTokens === true;
  const nextWidthPx = lineWidthPx + (lineHasTokens ? spaceWidthPx : 0) + tokenWidthPx;
  return {
    fits: nextWidthPx <= maxLinePx,
    nextWidthPx,
  };
}

module.exports = {
  deriveContentBox,
  canAppendToken,
};

