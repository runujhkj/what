function clampNumber(value, min, max, fallback) {
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  return Math.max(min, Math.min(max, n));
}

function normalizeBoxKey(value, allowedKeys) {
  const key = String(value || "").trim().toLowerCase();
  if (!key) return "";
  if (allowedKeys) {
    const allowed = Array.isArray(allowedKeys)
      ? allowedKeys
      : (typeof allowedKeys.has === "function" ? Array.from(allowedKeys) : Object.keys(allowedKeys));
    if (allowed.indexOf(key) !== -1) return key;
    return "";
  }
  if (key === "mic" || key === "desktop") return key;
  return "";
}

function normalizeLaneConstraint(cfg) {
  const src = cfg && typeof cfg === "object" ? cfg : {};
  return {
    linesLimit: clampNumber(src.linesLimit ?? src.maxSegments, 1, 10, 3),
    maxChars: clampNumber(src.maxChars, 20, 10000, 280),
    maxSegments: clampNumber(src.maxSegments, 1, 40, 3),
    widthPx: clampNumber(src.widthPx, 100, 4000, 640),
    paddingPx: clampNumber(src.paddingPx, 0, 120, 6),
    fontUi: clampNumber(src.fontUi, 0.1, 240, 3),
    maxLineChars: Number.isFinite(Number(src.maxLineChars))
      ? clampNumber(src.maxLineChars, 8, 240, 46)
      : null,
    maxLinePx: Number.isFinite(Number(src.maxLinePx))
      ? clampNumber(src.maxLinePx, 8, 4000, 0)
      : null,
    fitEpsilonPx: Number.isFinite(Number(src.fitEpsilonPx))
      ? clampNumber(src.fitEpsilonPx, 0, 200, 0)
      : null,
    noWordSplit: src.noWordSplit !== false,
  };
}

function buildSetTestStreamPayload(input) {
  const ctx = input && typeof input === "object" ? input : {};
  const box = normalizeBoxKey(ctx.box);
  const normalized = normalizeLaneConstraint(ctx.cfg);
  const out = {
    enabled: ctx.enabled !== false,
    box,
    linesLimit: normalized.linesLimit,
    maxChars: normalized.maxChars,
    maxSegments: normalized.maxSegments,
    widthPx: normalized.widthPx,
    paddingPx: normalized.paddingPx,
    fontUi: normalized.fontUi,
    noWordSplit: normalized.noWordSplit,
  };
  if (normalized.maxLineChars !== null && Number.isFinite(Number(normalized.maxLineChars))) {
    out.maxLineChars = Number(normalized.maxLineChars);
  }
  if (normalized.maxLinePx !== null && Number.isFinite(Number(normalized.maxLinePx))) {
    out.maxLinePx = Number(normalized.maxLinePx);
  }
  if (normalized.fitEpsilonPx !== null && Number.isFinite(Number(normalized.fitEpsilonPx))) {
    out.fitEpsilonPx = Number(normalized.fitEpsilonPx);
  }
  return out;
}

function shouldPreferFallbackGeometry(debugRaw) {
  const raw = debugRaw && typeof debugRaw === "object" ? debugRaw : {};
  const width = String(raw.width || "").trim();
  const font = String(raw.font || "").trim();
  const padding = String(raw.padding || "").trim();
  return width.length === 0 || font.length === 0 || padding.length === 0;
}

function mergeRuntimeConstraints(input) {
  const ctx = input && typeof input === "object" ? input : {};
  const incomingRaw = ctx.incoming && typeof ctx.incoming === "object" ? ctx.incoming : {};
  const incoming = normalizeLaneConstraint(incomingRaw);
  const fallbackRaw = ctx.fallback && typeof ctx.fallback === "object" ? ctx.fallback : {};
  const fallback = normalizeLaneConstraint(fallbackRaw);
  const preferFallbackGeometry = Boolean(ctx.preferFallbackGeometry);
  function hasFiniteValue(value) {
    if (value === null || typeof value === "undefined") return false;
    if (typeof value === "string" && value.trim() === "") return false;
    return Number.isFinite(Number(value));
  }

  const hasFallback = {
    linesLimit: hasFiniteValue(fallbackRaw.linesLimit),
    maxChars: hasFiniteValue(fallbackRaw.maxChars),
    maxSegments: hasFiniteValue(fallbackRaw.maxSegments),
    widthPx: hasFiniteValue(fallbackRaw.widthPx),
    paddingPx: hasFiniteValue(fallbackRaw.paddingPx),
    fontUi: hasFiniteValue(fallbackRaw.fontUi),
  };
  const hasIncoming = {
    linesLimit: hasFiniteValue(incomingRaw.linesLimit) || hasFiniteValue(incomingRaw.maxSegments),
    maxChars: hasFiniteValue(incomingRaw.maxChars),
    maxSegments: hasFiniteValue(incomingRaw.maxSegments),
    widthPx: hasFiniteValue(incomingRaw.widthPx),
    paddingPx: hasFiniteValue(incomingRaw.paddingPx),
    fontUi: hasFiniteValue(incomingRaw.fontUi),
  };

  const merged = {
    linesLimit: hasIncoming.linesLimit
      ? incoming.linesLimit
      : hasFallback.linesLimit
      ? fallback.linesLimit
      : incoming.linesLimit,
    maxChars: hasIncoming.maxChars
      ? incoming.maxChars
      : hasFallback.maxChars
      ? fallback.maxChars
      : incoming.maxChars,
    maxSegments: hasIncoming.maxSegments
      ? incoming.maxSegments
      : hasFallback.maxSegments
      ? fallback.maxSegments
      : incoming.maxSegments,
    widthPx: (!hasIncoming.widthPx && preferFallbackGeometry && hasFallback.widthPx) ? fallback.widthPx : incoming.widthPx,
    paddingPx: (!hasIncoming.paddingPx && preferFallbackGeometry && hasFallback.paddingPx) ? fallback.paddingPx : incoming.paddingPx,
    fontUi: (!hasIncoming.fontUi && preferFallbackGeometry && hasFallback.fontUi) ? fallback.fontUi : incoming.fontUi,
    noWordSplit: incoming.noWordSplit !== false && fallback.noWordSplit !== false,
  };

  // If geometry is stale, force main lane policy to derive maxLineChars from
  // corrected geometry instead of honoring stale caller-provided values.
  if (!preferFallbackGeometry && Number.isFinite(Number(incoming.maxLineChars))) {
    merged.maxLineChars = incoming.maxLineChars;
  }
  if (!preferFallbackGeometry && Number.isFinite(Number(incoming.maxLinePx))) {
    merged.maxLinePx = incoming.maxLinePx;
  }
  if (Number.isFinite(Number(incoming.fitEpsilonPx))) {
    merged.fitEpsilonPx = incoming.fitEpsilonPx;
  }
  return merged;
}

module.exports = {
  clampNumber,
  normalizeBoxKey,
  normalizeLaneConstraint,
  buildSetTestStreamPayload,
  shouldPreferFallbackGeometry,
  mergeRuntimeConstraints,
};
