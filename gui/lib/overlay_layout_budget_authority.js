function clampNumber(value, min, max, fallback) {
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  return Math.max(min, Math.min(max, n));
}

function deriveMaxLineCharsFromGeometry(input) {
  const ctx = input && typeof input === "object" ? input : {};
  const widthPx = clampNumber(ctx.widthPx, 100, 4000, 640);
  const paddingPx = clampNumber(ctx.paddingPx, 0, 120, 6);
  const fontUi = clampNumber(ctx.fontUi, 0.1, 240, 3);
  const contentWidthPx = Math.max(24, widthPx - (paddingPx * 2));
  // Empirical estimate for FT2 lane wrapping. A fixed base plus a font-scaled
  // term tracks observed per-glyph occupancy better than pure font scaling.
  const approxCharPx = Math.max(1.0, 8 + (fontUi * 0.9));
  return clampNumber(Math.floor(contentWidthPx / approxCharPx), 8, 240, 31);
}

function deriveMaxLineCharsFloorFromBudget(maxChars) {
  const safeChars = clampNumber(maxChars, 20, 10000, 280);
  // 280 -> 31; keeps historical stable behavior for test stream.
  return clampNumber(Math.floor(safeChars / 9), 16, 120, 31);
}

function deriveLaneBudget(input) {
  const ctx = input && typeof input === "object" ? input : {};
  const linesLimit = clampNumber(ctx.linesLimit, 1, 10, 3);
  const maxChars = clampNumber(ctx.maxChars, 20, 10000, 280);
  const maxSegments = clampNumber(ctx.maxSegments, 1, 40, linesLimit);
  const widthPx = clampNumber(ctx.widthPx, 100, 4000, 640);
  const paddingPx = clampNumber(ctx.paddingPx, 0, 120, 6);
  const fontUi = clampNumber(ctx.fontUi, 0.1, 240, 3);
  const noWordSplit = ctx.noWordSplit !== false;

  const explicitMaxLineChars = Number.isFinite(Number(ctx.maxLineChars))
    ? clampNumber(ctx.maxLineChars, 8, 240, 31)
    : null;
  const explicitMaxLinePx = Number.isFinite(Number(ctx.maxLinePx))
    ? clampNumber(ctx.maxLinePx, 8, 4000, 0)
    : null;
  const fitEpsilonPx = Number.isFinite(Number(ctx.fitEpsilonPx))
    ? clampNumber(ctx.fitEpsilonPx, 0, 200, 0)
    : 0;

  const geometryMaxLineChars = deriveMaxLineCharsFromGeometry({
    widthPx,
    paddingPx,
    fontUi,
  });
  const floorMaxLineChars = deriveMaxLineCharsFloorFromBudget(maxChars);
  // Geometry is authoritative for per-line wrap width; maxChars still governs
  // total retained content budget separately in the compositor.
  const derivedMaxLineChars = Math.max(8, geometryMaxLineChars);
  const maxLineChars = explicitMaxLineChars === null ? derivedMaxLineChars : explicitMaxLineChars;

  return {
    linesLimit,
    maxChars,
    maxSegments,
    maxLineChars,
    widthPx,
    paddingPx,
    fontUi,
    noWordSplit,
    contentWidthPx: Math.max(24, widthPx - (paddingPx * 2)),
    maxLinePx: explicitMaxLinePx === null
      ? Math.max(24, widthPx - (paddingPx * 2))
      : Math.max(8, explicitMaxLinePx - fitEpsilonPx),
    fitEpsilonPx,
    maxVisibleLines: linesLimit,
    derivation: {
      maxLineChars: explicitMaxLineChars === null ? "derived" : "incoming",
      maxLinePx: explicitMaxLinePx === null ? "derived" : "incoming",
      fitEpsilonPx: fitEpsilonPx > 0 ? "incoming" : "default",
      floorMaxLineChars,
      geometryMaxLineChars,
      explicitMaxLineChars,
      explicitMaxLinePx,
    },
  };
}

module.exports = {
  clampNumber,
  deriveMaxLineCharsFromGeometry,
  deriveMaxLineCharsFloorFromBudget,
  deriveLaneBudget,
};
