(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
    return;
  }
  root.whatGuiLineFreezeCompositor = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  let lineFitAuthority = null;
  try {
    if (typeof require === "function") {
      lineFitAuthority = require("./line_fit_authority");
    }
  } catch (_err) {
    lineFitAuthority = null;
  }

  function clampInt(value, min, max, fallback) {
    const n = Number(value);
    if (!Number.isFinite(n)) return fallback;
    return Math.max(min, Math.min(max, Math.floor(n)));
  }

  function normalizeConfig(input) {
    const src = input && typeof input === "object" ? input : {};
    const maxLines = clampInt(src.maxLines, 1, 10, 3);
    const maxChars = clampInt(src.maxChars, 20, 4000, 280);
    const maxSegments = clampInt(src.maxSegments, 1, 4000, maxLines);
    const noWordSplit = src.noWordSplit !== false;
    const preserveSegmentUnits = src.preserveSegmentUnits === true;
    const usePixelFit = src.usePixelFit === true;
    const fontUi = Number.isFinite(Number(src.fontUi))
      ? Math.max(0.1, Number(src.fontUi))
      : 3;
    const widthPx = Number.isFinite(Number(src.widthPx))
      ? Math.max(1, Number(src.widthPx))
      : 640;
    const heightPx = Number.isFinite(Number(src.heightPx))
      ? Math.max(1, Number(src.heightPx))
      : 140;
    const paddingPx = Number.isFinite(Number(src.paddingPx))
      ? Math.max(0, Number(src.paddingPx))
      : 6;
    const derivedContent = lineFitAuthority && typeof lineFitAuthority.deriveContentBox === "function"
      ? lineFitAuthority.deriveContentBox({ widthPx, heightPx, paddingPx })
      : {
          widthPx,
          heightPx,
          paddingPx,
          contentWidthPx: Math.max(1, widthPx - (paddingPx * 2)),
          contentHeightPx: Math.max(1, heightPx - (paddingPx * 2)),
        };
    const maxLinePx = Number.isFinite(Number(src.maxLinePx))
      ? Math.max(8, Number(src.maxLinePx))
      : Math.max(8, Number(derivedContent.contentWidthPx) || 24);
    const maxLineChars = clampInt(
      src.maxLineChars,
      8,
      4000,
      Math.max(8, Math.floor(maxChars / maxLines))
    );
    return {
      maxLines,
      maxChars,
      maxSegments,
      noWordSplit,
      preserveSegmentUnits,
      maxLineChars,
      maxLinePx,
      fontUi,
      usePixelFit,
      widthPx,
      heightPx,
      paddingPx,
      contentWidthPx: derivedContent.contentWidthPx,
      contentHeightPx: derivedContent.contentHeightPx,
    };
  }

  function estimateGlyphEm(ch) {
    const c = String(ch || "");
    if (c === " ") return 0.33;
    if (/[.,;:!'`|]/.test(c)) return 0.28;
    if (/[iljfrtI]/.test(c)) return 0.38;
    if (/[mwMW]/.test(c)) return 0.9;
    if (/[A-Z]/.test(c)) return 0.66;
    if (/[0-9]/.test(c)) return 0.56;
    return 0.56;
  }

  function estimateTextPx(text, fontUi) {
    const s = String(text || "");
    // Calibrated against OBS FT2 scene output for Helvetica-class fonts used
    // in the test stream lanes. A slightly higher scale prevents late wraps
    // that visually overflow before line rollover.
    const fontPx = Math.max(1, Number(fontUi) * 5.75);
    let em = 0;
    for (let i = 0; i < s.length; i += 1) em += estimateGlyphEm(s[i]);
    return em * fontPx;
  }

  function tokenize(text, noWordSplit, preserveSegmentUnits, segmentId) {
    const raw = String(text || "");
    if (!raw.trim()) return [];
    if (preserveSegmentUnits) return [{ text: raw.trim(), segmentId }];
    if (noWordSplit) {
      return raw.trim().split(/\s+/).filter(Boolean).map((tok) => ({ text: tok, segmentId }));
    }
    return raw.split("").map((tok) => ({ text: tok, segmentId }));
  }

  function lineText(tokens, noWordSplit) {
    const parts = Array.isArray(tokens) ? tokens.map((tok) => String(tok && tok.text ? tok.text : "")).filter(Boolean) : [];
    return noWordSplit ? parts.join(" ") : parts.join("");
  }

  function lineRepresentativeCount(tokens) {
    const reps = new Set();
    (Array.isArray(tokens) ? tokens : []).forEach((tok) => {
      const id = tok && tok.segmentId;
      if (id === null || id === undefined || id === "") return;
      reps.add(String(id));
    });
    return reps.size;
  }

  function lineState(tokens, noWordSplit) {
    return {
      text: lineText(tokens, noWordSplit),
      representativeCount: lineRepresentativeCount(tokens),
    };
  }

  function uniqueSegmentCountAcrossLines(sealedLines, activeTokens) {
    const ids = new Set();
    const collect = (tokens) => {
      (Array.isArray(tokens) ? tokens : []).forEach((tok) => {
        const id = tok && tok.segmentId;
        if (id === null || id === undefined || id === "") return;
        ids.add(String(id));
      });
    };
    (Array.isArray(sealedLines) ? sealedLines : []).forEach(collect);
    collect(activeTokens);
    return ids.size;
  }

  function createLineFreezeCompositor(input) {
    let config = normalizeConfig(input);
    const measureTextPx = input && typeof input.measureTextPx === "function"
      ? input.measureTextPx
      : null;
    let sealed = [];
    let activeTokens = [];
    let syntheticSegmentCounter = 0;

    function normalizeSegmentId(value) {
      if (value === null || value === undefined || value === "") {
        syntheticSegmentCounter += 1;
        return `auto-${syntheticSegmentCounter}`;
      }
      return String(value);
    }

    function evictOldestLine() {
      if (sealed.length > 0) {
        sealed.shift();
        return true;
      }
      if (activeTokens.length > 0) {
        activeTokens = [];
        return true;
      }
      return false;
    }

    function evictOldestSealedLine() {
      if (sealed.length <= 0) return false;
      sealed.shift();
      return true;
    }

    function trimOldestRepresentativeFromActive() {
      if (!activeTokens.length) return false;
      let oldestId = null;
      for (const tok of activeTokens) {
        const id = tok && tok.segmentId;
        if (id === null || id === undefined || id === "") continue;
        oldestId = String(id);
        break;
      }
      if (!oldestId) {
        activeTokens.shift();
        return true;
      }
      const next = activeTokens.filter((tok) => String(tok && tok.segmentId ? tok.segmentId : "") !== oldestId);
      if (next.length === activeTokens.length) return false;
      activeTokens = next;
      return true;
    }

    function trimOldestTokenFromActive() {
      if (!activeTokens.length) return false;
      activeTokens.shift();
      return true;
    }

    function snapshot() {
      const active = lineState(activeTokens, config.noWordSplit);
      const sealedStates = sealed.map((tokens) => lineState(tokens, config.noWordSplit));
      const lines = sealedStates.map((line) => line.text).concat(active.text ? [active.text] : []);
      const totalChars = lines.join(" ").length;
      const visibleRepresentatives = sealedStates.reduce((sum, line) => sum + line.representativeCount, 0)
        + (active.text ? active.representativeCount : 0);
      const uniqueVisibleSegments = uniqueSegmentCountAcrossLines(sealed, activeTokens);
      return {
        sealedLines: sealedStates.map((line) => line.text),
        activeLine: active.text,
        lines,
        totalChars,
        visibleRepresentatives,
        uniqueVisibleSegments,
        representativeCounts: {
          sealed: sealedStates.map((line) => line.representativeCount),
          active: active.representativeCount,
        },
        config: { ...config },
      };
    }

    function enforceLimits() {
      // Hard line budget.
      while (sealed.length + (activeTokens.length ? 1 : 0) > config.maxLines) {
        if (!evictOldestLine()) break;
      }

      // Hard char budget, evicting oldest full lines.
      let state = snapshot();
      while (state.totalChars > config.maxChars) {
        if (!evictOldestSealedLine()) {
          if (!trimOldestTokenFromActive()) break;
        }
        state = snapshot();
      }

      // Hard segment budget across sealed + active lines by segment representatives
      // (each line representation counts once, including split-segment carry-over).
      while (state.visibleRepresentatives > config.maxSegments) {
        if (!evictOldestSealedLine()) {
          if (!trimOldestRepresentativeFromActive()) break;
        }
        state = snapshot();
      }
    }

    function sealActiveLine() {
      const line = lineText(activeTokens, config.noWordSplit);
      if (line) sealed.push(activeTokens.slice());
      activeTokens = [];
    }

    function appendToken(token) {
      if (!token || !token.text) return;
      if (!activeTokens.length) {
        activeTokens.push({ ...token });
        return;
      }
      const current = lineText(activeTokens, config.noWordSplit);
      const candidate = config.noWordSplit ? `${current} ${token.text}` : `${current}${token.text}`;
      let fits = false;
      if (
        config.usePixelFit
        && Number.isFinite(Number(config.maxLinePx))
        && Number(config.maxLinePx) > 0
      ) {
        const currentMeasured = measureTextPx
          ? Number(measureTextPx(current, { fontUi: config.fontUi })) || 0
          : estimateTextPx(current, config.fontUi);
        const tokenMeasured = measureTextPx
          ? Number(measureTextPx(token.text, { fontUi: config.fontUi })) || 0
          : estimateTextPx(token.text, config.fontUi);
        const spaceMeasured = config.noWordSplit
          ? (measureTextPx
              ? Number(measureTextPx(" ", { fontUi: config.fontUi })) || 0
              : estimateTextPx(" ", config.fontUi))
          : 0;
        // In pixel-fit mode, measured width is authoritative. A secondary
        // char cap causes premature wraps when proportional glyph widths vary.
        const fitResult = lineFitAuthority && typeof lineFitAuthority.canAppendToken === "function"
          ? lineFitAuthority.canAppendToken({
              maxLinePx: Number(config.maxLinePx),
              lineWidthPx: currentMeasured,
              tokenWidthPx: tokenMeasured,
              spaceWidthPx: spaceMeasured,
              lineHasTokens: activeTokens.length > 0 && config.noWordSplit,
            })
          : {
              fits: (
                currentMeasured
                + ((activeTokens.length > 0 && config.noWordSplit) ? spaceMeasured : 0)
                + tokenMeasured
              ) <= Number(config.maxLinePx),
            };
        fits = fitResult.fits === true;
      } else {
        fits = candidate.length <= config.maxLineChars;
      }
      if (fits) {
        activeTokens.push({ ...token });
        return;
      }
      sealActiveLine();
      activeTokens.push({ ...token });
    }

    function appendSegment(text, meta) {
      const segmentId = normalizeSegmentId(meta && meta.segmentId);
      const tokens = tokenize(text, config.noWordSplit, config.preserveSegmentUnits, segmentId);
      for (const tok of tokens) appendToken(tok);
      enforceLimits();
      return snapshot();
    }

    function setConstraints(partial) {
      const retained = [];
      sealed.forEach((lineTokens) => {
        if (Array.isArray(lineTokens)) retained.push(...lineTokens);
      });
      if (Array.isArray(activeTokens) && activeTokens.length > 0) retained.push(...activeTokens);
      config = normalizeConfig({ ...config, ...(partial || {}) });
      sealed = [];
      activeTokens = [];
      retained.forEach((tok) => appendToken(tok));
      enforceLimits();
      return snapshot();
    }

    function evictOldestLines(count) {
      let remaining = clampInt(count, 1, 1000, 1);
      while (remaining > 0) {
        if (!evictOldestLine()) break;
        remaining -= 1;
      }
      enforceLimits();
      return snapshot();
    }

    function evictOldestSealedLines(count) {
      let remaining = clampInt(count, 1, 1000, 1);
      while (remaining > 0 && sealed.length > 0) {
        sealed.shift();
        remaining -= 1;
      }
      enforceLimits();
      return snapshot();
    }

    function reset() {
      sealed = [];
      activeTokens = [];
      return snapshot();
    }

    return {
      appendSegment,
      setConstraints,
      evictOldestLines,
      evictOldestSealedLines,
      getState: snapshot,
      reset,
    };
  }

  return { createLineFreezeCompositor };
});
