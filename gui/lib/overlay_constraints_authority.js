(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory(require("./overlay_box_runtime"));
    return;
  }
  root.whatGuiOverlayConstraintsAuthority = factory(root.whatGuiOverlayBoxRuntime || null);
})(typeof globalThis !== "undefined" ? globalThis : this, function (overlayBoxRuntime) {
  function normalizeBoxKey(value, allowedKeys) {
    if (overlayBoxRuntime && typeof overlayBoxRuntime.normalizeBoxKey === "function") {
      return overlayBoxRuntime.normalizeBoxKey(value, allowedKeys);
    }
    const key = String(value || "").trim().toLowerCase();
    if (!key) return "";
    if (allowedKeys) {
      const allowed = Array.isArray(allowedKeys)
        ? allowedKeys
        : (typeof allowedKeys.has === "function" ? Array.from(allowedKeys) : Object.keys(allowedKeys));
      return allowed.indexOf(key) !== -1 ? key : "";
    }
    if (key === "mic" || key === "desktop") return key;
    return "";
  }

  function clampNumber(value, min, max, fallback) {
    if (overlayBoxRuntime && typeof overlayBoxRuntime.clampNumber === "function") {
      return overlayBoxRuntime.clampNumber(value, min, max, fallback);
    }
    const n = Number(value);
    if (!Number.isFinite(n)) return fallback;
    return Math.max(min, Math.min(max, n));
  }

  function normalizeLaneConstraint(cfg) {
    if (overlayBoxRuntime && typeof overlayBoxRuntime.normalizeLaneConstraint === "function") {
      return overlayBoxRuntime.normalizeLaneConstraint(cfg);
    }
    const src = cfg && typeof cfg === "object" ? cfg : {};
    return {
      linesLimit: clampNumber(src.maxSegments, 1, 10, 3),
      maxChars: clampNumber(src.maxChars, 20, 10000, 280),
      maxSegments: clampNumber(src.maxSegments, 1, 40, 3),
      widthPx: clampNumber(src.widthPx, 100, 4000, 640),
      paddingPx: clampNumber(src.paddingPx, 0, 120, 6),
      fontUi: clampNumber(src.fontUi, 0.1, 240, 3),
      noWordSplit: src.noWordSplit !== false,
    };
  }

  function buildSetTestStreamPayload(input) {
    if (overlayBoxRuntime && typeof overlayBoxRuntime.buildSetTestStreamPayload === "function") {
      return overlayBoxRuntime.buildSetTestStreamPayload(input);
    }
    const ctx = input && typeof input === "object" ? input : {};
    const box = normalizeBoxKey(ctx.box);
    const normalized = normalizeLaneConstraint(ctx.cfg);
    return {
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
  }

  function buildSetTestStreamPayloads(input) {
    const ctx = input && typeof input === "object" ? input : {};
    const boxes = ctx.boxes && typeof ctx.boxes === "object" ? ctx.boxes : {};
    const sourceKeys = Array.isArray(ctx.sourceKeys) && ctx.sourceKeys.length > 0
      ? ctx.sourceKeys
      : Object.keys(boxes).length > 0
        ? Object.keys(boxes)
        : ["mic", "desktop"];
    return sourceKeys.map((box) => {
      const cfg = boxes[box] && typeof boxes[box] === "object" ? boxes[box] : {};
      return buildSetTestStreamPayload({
        enabled: ctx.enabled !== false,
        box,
        cfg,
      });
    });
  }

  function parseFiniteAtLeast(value, min) {
    if (value === null || typeof value === "undefined") return null;
    if (typeof value === "string" && value.trim() === "") return null;
    const n = Number(value);
    if (!Number.isFinite(n)) return null;
    return n >= min ? n : null;
  }

  function buildConstraintPatch(input) {
    const ctx = input && typeof input === "object" ? input : {};
    const patch = {
      box: normalizeBoxKey(ctx.box),
      noWordSplit: ctx.noWordSplit !== false,
    };
    const hasExplicitNoWordSplit = Object.prototype.hasOwnProperty.call(ctx, "noWordSplit");
    const linesLimit = parseFiniteAtLeast(ctx.linesLimit, 1);
    const maxChars = parseFiniteAtLeast(ctx.maxChars, 20);
    const maxSegments = parseFiniteAtLeast(ctx.maxSegments, 1);
    const widthPx = parseFiniteAtLeast(ctx.widthPx, 100);
    const paddingPx = parseFiniteAtLeast(ctx.paddingPx, 0);
    const fontUi = parseFiniteAtLeast(ctx.fontUi, 0.1);
    const maxLineChars = parseFiniteAtLeast(ctx.maxLineChars, 8);
    const maxLinePx = parseFiniteAtLeast(ctx.maxLinePx, 8);
    const fitEpsilonPx = parseFiniteAtLeast(ctx.fitEpsilonPx, 0);

    if (linesLimit !== null) patch.linesLimit = linesLimit;
    if (maxChars !== null) patch.maxChars = maxChars;
    if (maxSegments !== null) patch.maxSegments = maxSegments;
    if (widthPx !== null) patch.widthPx = widthPx;
    if (paddingPx !== null) patch.paddingPx = paddingPx;
    if (fontUi !== null) patch.fontUi = fontUi;
    if (maxLineChars !== null) patch.maxLineChars = maxLineChars;
    if (maxLinePx !== null) patch.maxLinePx = maxLinePx;
    if (fitEpsilonPx !== null) patch.fitEpsilonPx = fitEpsilonPx;

    const hasNumericConstraints = linesLimit !== null
      || maxChars !== null
      || maxSegments !== null
      || widthPx !== null
      || paddingPx !== null
      || fontUi !== null
      || maxLineChars !== null
      || maxLinePx !== null
      || fitEpsilonPx !== null;
    const hasAuthorityTrace = Boolean(ctx.authorityTrace && typeof ctx.authorityTrace === "object");
    if (hasAuthorityTrace) {
      patch.authorityTrace = { ...ctx.authorityTrace };
    }

    return {
      patch,
      hasConstraintPatch: hasNumericConstraints || hasExplicitNoWordSplit || hasAuthorityTrace,
    };
  }

  function mergeRuntimeLaneConstraint(input) {
    const ctx = input && typeof input === "object" ? input : {};
    const incomingRaw = ctx.incoming && typeof ctx.incoming === "object" ? ctx.incoming : {};
    const fallbackRaw = ctx.fallback && typeof ctx.fallback === "object" ? ctx.fallback : {};
    const debugRaw = ctx.debugRaw && typeof ctx.debugRaw === "object" ? ctx.debugRaw : {};
    function hasFiniteValue(value) {
      if (value === null || typeof value === "undefined") return false;
      if (typeof value === "string" && value.trim() === "") return false;
      return Number.isFinite(Number(value));
    }

    const incomingHas = {
      linesLimit: hasFiniteValue(incomingRaw.linesLimit) || hasFiniteValue(incomingRaw.maxSegments),
      maxChars: hasFiniteValue(incomingRaw.maxChars),
      maxSegments: hasFiniteValue(incomingRaw.maxSegments),
      widthPx: hasFiniteValue(incomingRaw.widthPx),
      paddingPx: hasFiniteValue(incomingRaw.paddingPx),
      fontUi: hasFiniteValue(incomingRaw.fontUi),
      maxLineChars: hasFiniteValue(incomingRaw.maxLineChars),
      maxLinePx: hasFiniteValue(incomingRaw.maxLinePx),
      fitEpsilonPx: hasFiniteValue(incomingRaw.fitEpsilonPx),
    };
    const fallbackHas = {
      linesLimit: hasFiniteValue(fallbackRaw.linesLimit),
      maxChars: hasFiniteValue(fallbackRaw.maxChars),
      maxSegments: hasFiniteValue(fallbackRaw.maxSegments),
      widthPx: hasFiniteValue(fallbackRaw.widthPx),
      paddingPx: hasFiniteValue(fallbackRaw.paddingPx),
      fontUi: hasFiniteValue(fallbackRaw.fontUi),
    };
    const preferFallbackGeometry = (
      overlayBoxRuntime && typeof overlayBoxRuntime.shouldPreferFallbackGeometry === "function"
    )
      ? overlayBoxRuntime.shouldPreferFallbackGeometry({
        width: String(debugRaw.width || ""),
        font: String(debugRaw.font || ""),
        padding: String(debugRaw.padding || ""),
      })
      : false;

    if (overlayBoxRuntime && typeof overlayBoxRuntime.mergeRuntimeConstraints === "function") {
      const merged = overlayBoxRuntime.mergeRuntimeConstraints({
        incoming: incomingRaw,
        fallback: fallbackRaw,
        preferFallbackGeometry,
      });
      return {
        ...merged,
        authorityTrace: {
          preferFallbackGeometry,
          linesLimit: incomingHas.linesLimit ? "incoming" : (fallbackHas.linesLimit ? "fallback" : "default"),
          maxChars: incomingHas.maxChars ? "incoming" : (fallbackHas.maxChars ? "fallback" : "default"),
          maxSegments: incomingHas.maxSegments ? "incoming" : (fallbackHas.maxSegments ? "fallback" : "default"),
          widthPx: (!incomingHas.widthPx && preferFallbackGeometry && fallbackHas.widthPx) ? "fallback" : "incoming",
          paddingPx: (!incomingHas.paddingPx && preferFallbackGeometry && fallbackHas.paddingPx) ? "fallback" : "incoming",
          fontUi: (!incomingHas.fontUi && preferFallbackGeometry && fallbackHas.fontUi) ? "fallback" : "incoming",
          maxLineChars: (!preferFallbackGeometry && incomingHas.maxLineChars) ? "incoming" : "derived",
          maxLinePx: (!preferFallbackGeometry && incomingHas.maxLinePx) ? "incoming" : "derived",
          fitEpsilonPx: incomingHas.fitEpsilonPx ? "incoming" : "default",
        },
      };
    }
    const merged = normalizeLaneConstraint(incomingRaw);
    return {
      ...merged,
      authorityTrace: {
        preferFallbackGeometry: false,
        linesLimit: incomingHas.linesLimit ? "incoming" : "default",
        maxChars: incomingHas.maxChars ? "incoming" : "default",
        maxSegments: incomingHas.maxSegments ? "incoming" : "default",
        widthPx: incomingHas.widthPx ? "incoming" : "default",
        paddingPx: incomingHas.paddingPx ? "incoming" : "default",
        fontUi: incomingHas.fontUi ? "incoming" : "default",
        maxLineChars: incomingHas.maxLineChars ? "incoming" : "derived",
        maxLinePx: incomingHas.maxLinePx ? "incoming" : "derived",
        fitEpsilonPx: incomingHas.fitEpsilonPx ? "incoming" : "default",
      },
    };
  }

  return {
    normalizeBoxKey,
    clampNumber,
    normalizeLaneConstraint,
    parseFiniteAtLeast,
    buildConstraintPatch,
    mergeRuntimeLaneConstraint,
    buildSetTestStreamPayload,
    buildSetTestStreamPayloads,
  };
});
