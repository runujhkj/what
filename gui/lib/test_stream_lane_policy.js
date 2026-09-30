const lineFreezeCompositor = require("./line_freeze_compositor");
const layoutBudgetAuthority = require("./overlay_layout_budget_authority");

function clamp(value, min, max, fallback) {
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  return Math.max(min, Math.min(max, Math.floor(n)));
}

function normalizeBox(value) {
  const key = String(value || "").trim().toLowerCase();
  if (key === "mic" || key === "desktop") return key;
  return "";
}

  function createTestStreamLanePolicy(input) {
  const ctx = input && typeof input === "object" ? input : {};
  const defaultLinesLimit = clamp(ctx.linesLimit, 1, 10, 3);
  const defaultMaxChars = Math.max(20, Number(ctx.maxChars) || 280);
  const deriveLaneBudget = typeof ctx.deriveLaneBudget === "function"
    ? ctx.deriveLaneBudget
    : (input) => {
      // Backward-compatible test hook: allow legacy custom max-line-char derivation.
      if (typeof ctx.deriveMaxLineChars === "function" && input && input._initial === true) {
        const base = layoutBudgetAuthority.deriveLaneBudget(input);
        const derived = ctx.deriveMaxLineChars(base.maxChars, base.linesLimit);
        return {
          ...base,
          maxLineChars: clamp(derived, 8, 240, base.maxLineChars),
          derivation: {
            ...(base.derivation || {}),
            maxLineChars: "legacy-derive-max-line-chars",
          },
        };
      }
      return layoutBudgetAuthority.deriveLaneBudget(input);
    };
  const usePixelFit = ctx.usePixelFit === true;

  function makeLane() {
    const budget = deriveLaneBudget({
      linesLimit: defaultLinesLimit,
      maxChars: defaultMaxChars,
      maxSegments: defaultLinesLimit,
      widthPx: 640,
      paddingPx: 6,
      fontUi: 3,
      noWordSplit: true,
      _initial: true,
    });
    return {
      enabled: false,
      constraints: {
        linesLimit: budget.linesLimit,
        maxChars: budget.maxChars,
        maxLineChars: budget.maxLineChars,
        segmentLimit: budget.maxSegments,
        widthPx: budget.widthPx,
        paddingPx: budget.paddingPx,
        fontUi: budget.fontUi,
        maxLinePx: budget.contentWidthPx,
        fitEpsilonPx: budget.fitEpsilonPx,
        noWordSplit: budget.noWordSplit,
        contentWidthPx: budget.contentWidthPx,
        maxVisibleLines: budget.maxVisibleLines,
        derivation: budget.derivation,
        authorityTrace: null,
      },
      segmentWindow: [],
      segmentSeq: 0,
      compositor: lineFreezeCompositor.createLineFreezeCompositor({
        maxLines: budget.linesLimit,
        maxChars: budget.maxChars,
        maxSegments: budget.maxSegments,
        maxLineChars: budget.maxLineChars,
        maxLinePx: budget.contentWidthPx,
        fontUi: budget.fontUi,
        usePixelFit,
        noWordSplit: budget.noWordSplit,
        preserveSegmentUnits: false,
      }),
    };
  }

  const lanes = {
    mic: makeLane(),
    desktop: makeLane(),
  };

  function laneKeys(box) {
    const key = normalizeBox(box);
    if (key) return [key];
    return ["mic", "desktop"];
  }

  function currentLines(key) {
    const state = lanes[key].compositor.getState();
    const raw = Array.isArray(state.lines) ? state.lines.slice() : [];
    return raw;
  }

  function sameConstraints(a, b) {
    const traceA = a && a.authorityTrace && typeof a.authorityTrace === "object" ? a.authorityTrace : null;
    const traceB = b && b.authorityTrace && typeof b.authorityTrace === "object" ? b.authorityTrace : null;
    const traceEqual = JSON.stringify(traceA || {}) === JSON.stringify(traceB || {});
    if (!a || !b) return false;
    return a.linesLimit === b.linesLimit
      && a.maxChars === b.maxChars
      && a.maxLineChars === b.maxLineChars
      && a.segmentLimit === b.segmentLimit
      && a.widthPx === b.widthPx
      && a.paddingPx === b.paddingPx
      && a.fontUi === b.fontUi
      && a.maxLinePx === b.maxLinePx
      && a.fitEpsilonPx === b.fitEpsilonPx
      && a.contentWidthPx === b.contentWidthPx
      && a.maxVisibleLines === b.maxVisibleLines
      && a.noWordSplit === b.noWordSplit
      && traceEqual;
  }

  function setEnabled(next, box) {
    const value = Boolean(next);
    laneKeys(box).forEach((key) => {
      const lane = lanes[key];
      lane.enabled = value;
      if (!value) {
        lane.segmentWindow = [];
        lane.segmentSeq = 0;
        lane.compositor.reset();
      }
    });
  }

  function setConstraints(next) {
    const src = next && typeof next === "object" ? next : {};
    laneKeys(src.box).forEach((key) => {
      const lane = lanes[key];
      const prev = lane.constraints;
      const linesLimit = clamp(src.linesLimit, 1, 10, prev.linesLimit);
      const maxChars = Math.max(20, Number(src.maxChars) || prev.maxChars);
      const widthPx = Math.max(100, Number(src.widthPx) || prev.widthPx || 640);
      const paddingPx = Math.max(0, Number(src.paddingPx) || prev.paddingPx || 6);
      const fontUi = Math.max(0.1, Number(src.fontUi) || prev.fontUi || 3);
      const noWordSplit = src.noWordSplit !== false;
      const authorityTrace = src.authorityTrace && typeof src.authorityTrace === "object"
        ? { ...src.authorityTrace }
        : prev.authorityTrace;
      const budget = deriveLaneBudget({
        linesLimit,
        maxChars,
        maxSegments: src.maxSegments,
        widthPx,
        paddingPx,
        fontUi,
        noWordSplit,
        maxLineChars: src.maxLineChars,
        maxLinePx: src.maxLinePx,
        fitEpsilonPx: src.fitEpsilonPx,
      });
      const nextConstraints = {
        linesLimit: budget.linesLimit,
        maxChars: budget.maxChars,
        maxLineChars: budget.maxLineChars,
        segmentLimit: budget.maxSegments,
        widthPx: budget.widthPx,
        paddingPx: budget.paddingPx,
        fontUi: budget.fontUi,
        noWordSplit: budget.noWordSplit,
        maxLinePx: budget.maxLinePx,
        fitEpsilonPx: budget.fitEpsilonPx,
        contentWidthPx: budget.contentWidthPx,
        maxVisibleLines: budget.maxVisibleLines,
        derivation: budget.derivation,
        authorityTrace,
      };
      if (sameConstraints(prev, nextConstraints)) return;
      lane.constraints = nextConstraints;
      lane.compositor.setConstraints({
        maxLines: budget.linesLimit,
        maxChars: budget.maxChars,
        maxSegments: budget.maxSegments,
        maxLineChars: budget.maxLineChars,
        maxLinePx: budget.maxLinePx,
        fontUi: budget.fontUi,
        usePixelFit,
        noWordSplit: budget.noWordSplit,
        preserveSegmentUnits: false,
      });
    });
  }

  function append(box, segment, meta) {
    const key = normalizeBox(box);
    if (!key) return [];
    const lane = lanes[key];
    if (!lane.enabled) return currentLines(key);

    const text = String(segment || "").trim();
    if (!text) return currentLines(key);

    lane.segmentSeq += 1;
    const explicitId = meta && meta.segmentId !== undefined ? meta.segmentId : null;
    const segmentId = explicitId === null ? `${key}-seg-${lane.segmentSeq}` : String(explicitId);
    lane.segmentWindow.push(text);
    if (lane.segmentWindow.length > 500) lane.segmentWindow = lane.segmentWindow.slice(-500);
    lane.compositor.appendSegment(text, { segmentId });
    return currentLines(key);
  }

  function reset() {
    Object.keys(lanes).forEach((key) => {
      lanes[key].segmentWindow = [];
      lanes[key].compositor.reset();
    });
  }

  function getState() {
    return {
      mic: {
        enabled: lanes.mic.enabled,
        constraints: { ...lanes.mic.constraints },
        segmentWindow: lanes.mic.segmentWindow.slice(),
        lines: currentLines("mic"),
      },
      desktop: {
        enabled: lanes.desktop.enabled,
        constraints: { ...lanes.desktop.constraints },
        segmentWindow: lanes.desktop.segmentWindow.slice(),
        lines: currentLines("desktop"),
      },
    };
  }

  return {
    append,
    setEnabled,
    setConstraints,
    reset,
    getState,
    anyEnabled: () => lanes.mic.enabled || lanes.desktop.enabled,
    laneEnabled: (box) => {
      const key = normalizeBox(box);
      return key ? lanes[key].enabled : false;
    },
    laneLines: (box) => {
      const key = normalizeBox(box);
      return key ? currentLines(key) : [];
    },
    laneConstraints: (box) => {
      const key = normalizeBox(box);
      return key ? { ...lanes[key].constraints } : null;
    },
  };
}

module.exports = {
  createTestStreamLanePolicy,
};
