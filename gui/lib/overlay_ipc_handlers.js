const overlayConstraintsAuthority = require("./overlay_constraints_authority");

function registerOverlayIpcHandlers({
  ipcMain,
  normalizeOverlayPayload,
  getOverlayPayload,
  setOverlayPayload,
  overlayClients,
  overlayPayloadForBox,
  encodeOverlay,
  getOverlayPort,
  getMainWindow,
  getOverlayTestStreamEnabled,
  setOverlayTestStreamEnabled
}) {
  function parseFiniteNumber(value) {
    if (value === null || typeof value === "undefined") return null;
    if (typeof value === "string" && value.trim() === "") return null;
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }

  function _renderSignatureForBody(body) {
    const b = body && typeof body === "object" ? body : {};
    return {
      ...(b.captionStream ? { captionStream: b.captionStream } : {}),
      text: String(b.text || ""),
      lines: Array.isArray(b.lines) ? b.lines.map((x) => String(x || "")) : [],
      transition: String(b.transition || "none"),
      enterLine: String(b.enterLine || ""),
      header: String(b.header || ""),
      width: String(b.width || ""),
      height: String(b.height || ""),
      fontSize: String(b.fontSize || ""),
      padding: String(b.padding || ""),
      textColor: String(b.textColor || ""),
      bgColor: String(b.bgColor || ""),
      noWordSplit: b.noWordSplit !== false,
    };
  }

  function _renderSignature(payload) {
    const p = payload && typeof payload === "object" ? payload : {};
    const boxes = p.boxes && typeof p.boxes === "object" ? p.boxes : {};
    return JSON.stringify({
      root: _renderSignatureForBody(p),
      mic: _renderSignatureForBody(boxes.mic),
      desktop: _renderSignatureForBody(boxes.desktop),
    });
  }

  let _lastRenderSignature = "";
  let _dedupSkipCount = 0;
  let _dedupSkipLastLogMs = 0;
  const DEDUP_SKIP_LOG_INTERVAL_MS = 5000;

  function readOverlayBoxConfigNumber(boxKey, field) {
    const payload = getOverlayPayload && typeof getOverlayPayload === "function"
      ? getOverlayPayload()
      : null;
    if (!payload || typeof payload !== "object") return null;
    const boxes = payload.boxes && typeof payload.boxes === "object" ? payload.boxes : {};
    const box = boxes[boxKey] && typeof boxes[boxKey] === "object" ? boxes[boxKey] : null;
    if (!box) return null;
    const cfg = box.config && typeof box.config === "object" ? box.config : {};
    return parseFiniteNumber(cfg[field]);
  }

  function coerceEnabled(value) {
    if (typeof value === "string") {
      const token = value.trim().toLowerCase();
      if (token === "false" || token === "0" || token === "off" || token === "no") return false;
      if (token === "true" || token === "1" || token === "on" || token === "yes") return true;
    }
    return Boolean(value);
  }

  function isBodyEmpty(body) {
    if (!body || typeof body !== "object") return true;
    const lines = Array.isArray(body.lines) ? body.lines : [];
    const text = String(body.text || "").trim();
    return lines.length === 0 && text.length === 0;
  }

  function cloneBodyFromPrevious(nextBody, prevBody) {
    const next = nextBody && typeof nextBody === "object" ? nextBody : {};
    const prev = prevBody && typeof prevBody === "object" ? prevBody : {};
    return {
      ...next,
      text: String(prev.text || ""),
      fullText: String(prev.fullText || prev.text || ""),
      lines: Array.isArray(prev.lines) ? prev.lines.slice() : [],
      segments: Array.isArray(prev.segments) ? prev.segments.slice() : [],
      segmentSpans: Array.isArray(prev.segmentSpans) ? prev.segmentSpans.slice() : [],
    };
  }

  function mergeOverlayPayloadContinuity(prevPayload, nextPayload) {
    const prev = prevPayload && typeof prevPayload === "object" ? prevPayload : {};
    const next = nextPayload && typeof nextPayload === "object" ? nextPayload : {};
    const out = { ...next };
    if (isBodyEmpty(next) && !isBodyEmpty(prev)) {
      Object.assign(out, cloneBodyFromPrevious(next, prev));
    }
    const prevBoxes = prev.boxes && typeof prev.boxes === "object" ? prev.boxes : {};
    const nextBoxes = next.boxes && typeof next.boxes === "object" ? next.boxes : {};
    const outBoxes = { ...nextBoxes };
    ["mic", "desktop"].forEach((key) => {
      const p = prevBoxes[key];
      const n = nextBoxes[key];
      if (!n || typeof n !== "object") {
        if (p && typeof p === "object") outBoxes[key] = { ...p };
        return;
      }
      if (isBodyEmpty(n) && !isBodyEmpty(p)) {
        outBoxes[key] = cloneBodyFromPrevious(n, p);
      }
    });
    out.boxes = outBoxes;
    return out;
  }

  ipcMain.handle("set-overlay-text", async (_event, payload) => {
    const normalized = normalizeOverlayPayload(payload);
    // Explicit lifecycle clears must not resurrect the previous session body.
    const mergedContinuity = payload?.clear === true
      ? normalized
      : mergeOverlayPayloadContinuity(getOverlayPayload(), normalized);
    const nextSig = _renderSignature(mergedContinuity);
    const unchanged = _lastRenderSignature && _lastRenderSignature === nextSig;
    if (unchanged) {
      try {
        _dedupSkipCount += 1;
        const seq = Number(mergedContinuity && mergedContinuity.seq) || -1;
        const traceId = String((mergedContinuity && mergedContinuity.trace_id) || "");
        const nowMs = Date.now();
        if ((nowMs - _dedupSkipLastLogMs) >= DEDUP_SKIP_LOG_INTERVAL_MS) {
          // eslint-disable-next-line no-console
          console.log(
            `what_gui: set-overlay-text dedup_skip count=${_dedupSkipCount} last_seq=${seq} trace='${traceId}'`
          );
          _dedupSkipCount = 0;
          _dedupSkipLastLogMs = nowMs;
        }
      } catch (_err) {
        // ignore telemetry formatting failures
      }
      return { ok: true, url: `http://127.0.0.1:${getOverlayPort()}/overlay`, skipped: true };
    }
    if (_dedupSkipCount > 0) {
      try {
        const nowMs = Date.now();
        if ((nowMs - _dedupSkipLastLogMs) >= DEDUP_SKIP_LOG_INTERVAL_MS) {
          // eslint-disable-next-line no-console
          console.log(`what_gui: set-overlay-text dedup_skip count=${_dedupSkipCount} (flush)`);
          _dedupSkipCount = 0;
          _dedupSkipLastLogMs = nowMs;
        }
      } catch (_err) {
        // ignore telemetry formatting failures
      }
    }
    try {
      const seq = Number(mergedContinuity && mergedContinuity.seq) || -1;
      const linesN = Array.isArray(mergedContinuity && mergedContinuity.lines) ? mergedContinuity.lines.length : 0;
      const rootSegN = Array.isArray(mergedContinuity && mergedContinuity.segments)
        ? mergedContinuity.segments.length
        : 0;
      const micLinesN = Array.isArray(mergedContinuity && mergedContinuity.boxes && mergedContinuity.boxes.mic && mergedContinuity.boxes.mic.lines)
        ? mergedContinuity.boxes.mic.lines.length
        : 0;
      const micSegN = Array.isArray(mergedContinuity && mergedContinuity.boxes && mergedContinuity.boxes.mic && mergedContinuity.boxes.mic.segments)
        ? mergedContinuity.boxes.mic.segments.length
        : 0;
      const desktopLinesN = Array.isArray(mergedContinuity && mergedContinuity.boxes && mergedContinuity.boxes.desktop && mergedContinuity.boxes.desktop.lines)
        ? mergedContinuity.boxes.desktop.lines.length
        : 0;
      const desktopSegN = Array.isArray(mergedContinuity && mergedContinuity.boxes && mergedContinuity.boxes.desktop && mergedContinuity.boxes.desktop.segments)
        ? mergedContinuity.boxes.desktop.segments.length
        : 0;
      const micCfgSeg = parseFiniteNumber(
        mergedContinuity
        && mergedContinuity.boxes
        && mergedContinuity.boxes.mic
        && mergedContinuity.boxes.mic.config
        && mergedContinuity.boxes.mic.config.maxSegments
      );
      const deskCfgSeg = parseFiniteNumber(
        mergedContinuity
        && mergedContinuity.boxes
        && mergedContinuity.boxes.desktop
        && mergedContinuity.boxes.desktop.config
        && mergedContinuity.boxes.desktop.config.maxSegments
      );
      const micCfgChars = parseFiniteNumber(
        mergedContinuity
        && mergedContinuity.boxes
        && mergedContinuity.boxes.mic
        && mergedContinuity.boxes.mic.config
        && mergedContinuity.boxes.mic.config.maxChars
      );
      const deskCfgChars = parseFiniteNumber(
        mergedContinuity
        && mergedContinuity.boxes
        && mergedContinuity.boxes.desktop
        && mergedContinuity.boxes.desktop.config
        && mergedContinuity.boxes.desktop.config.maxChars
      );
      const traceId = String((mergedContinuity && mergedContinuity.trace_id) || "");
      const micFirst = Array.isArray(mergedContinuity && mergedContinuity.boxes && mergedContinuity.boxes.mic && mergedContinuity.boxes.mic.lines)
        ? String(mergedContinuity.boxes.mic.lines[0] || "")
        : "";
      const deskFirst = Array.isArray(mergedContinuity && mergedContinuity.boxes && mergedContinuity.boxes.desktop && mergedContinuity.boxes.desktop.lines)
        ? String(mergedContinuity.boxes.desktop.lines[0] || "")
        : "";
      // eslint-disable-next-line no-console
      const clientsN = overlayClients && typeof overlayClients.size === "number" ? overlayClients.size : -1;
      console.log(
        `what_gui: set-overlay-text seq=${seq} root_l=${linesN} root_s=${rootSegN} mic_l=${micLinesN} mic_s=${micSegN} desk_l=${desktopLinesN} desk_s=${desktopSegN} ` +
        `mic_cfg_s=${micCfgSeg !== null ? micCfgSeg : "-"} desk_cfg_s=${deskCfgSeg !== null ? deskCfgSeg : "-"} ` +
        `mic_cfg_c=${micCfgChars !== null ? micCfgChars : "-"} desk_cfg_c=${deskCfgChars !== null ? deskCfgChars : "-"} ` +
        `trace='${traceId}' mic_first='${micFirst}' desk_first='${deskFirst}' port=${getOverlayPort()} clients=${clientsN}`
      );
    } catch (_err) {
      // ignore telemetry formatting failures
    }
    setOverlayPayload(mergedContinuity);
    _lastRenderSignature = nextSig;
    overlayClients.forEach((boxKey, res) => {
      try {
        res.write(`data: ${encodeOverlay(overlayPayloadForBox(boxKey, getOverlayPayload()))}\n\n`);
      } catch (_err) {
        // ignore
      }
    });
    return { ok: true, url: `http://127.0.0.1:${getOverlayPort()}/overlay` };
  });

  ipcMain.handle("get-overlay-url", async () => {
    return {
      ok: true,
      url: `http://127.0.0.1:${getOverlayPort()}/overlay`,
      events_url: `http://127.0.0.1:${getOverlayPort()}/events`,
      mic_url: `http://127.0.0.1:${getOverlayPort()}/events?box=mic`,
      desktop_url: `http://127.0.0.1:${getOverlayPort()}/events?box=desktop`
    };
  });

  ipcMain.handle("set-test-stream", async (_event, enabled) => {
    const payload = enabled && typeof enabled === "object" ? enabled : null;
    const payloadBox = payload ? String(payload.box || "").trim().toLowerCase() : "";
    const payloadLines = payload ? Number(payload.linesLimit) : NaN;
    const payloadMaxChars = payload ? Number(payload.maxChars) : NaN;
    const payloadMaxSegments = payload ? Number(payload.maxSegments) : NaN;
    const payloadWidth = payload ? Number(payload.widthPx) : NaN;
    const payloadPadding = payload ? Number(payload.paddingPx) : NaN;
    const payloadFont = payload ? Number(payload.fontUi) : NaN;
    const payloadMaxLine = payload ? Number(payload.maxLineChars) : NaN;
    const payloadMaxLinePx = payload ? Number(payload.maxLinePx) : NaN;
    const payloadFitEpsilonPx = payload ? Number(payload.fitEpsilonPx) : NaN;
    const payloadNoWordSplit = payload ? (payload.noWordSplit !== false) : true;
    const payloadDbgRawWidth = payload ? String(payload._debug_box_raw_width || "") : "";
    const payloadDbgRawFont = payload ? String(payload._debug_box_raw_font || "") : "";
    const payloadDbgRawPadding = payload ? String(payload._debug_box_raw_padding || "") : "";
    const payloadDbgRawSeg = payload ? String(payload._debug_box_raw_max_segments || "") : "";
    const payloadDbgRawChars = payload ? String(payload._debug_box_raw_max_chars || "") : "";
    if (enabled && typeof enabled === "object") {
      const box = overlayConstraintsAuthority.normalizeBoxKey(enabled.box);
      let linesLimit = Number(enabled.linesLimit);
      let maxChars = Number(enabled.maxChars);
      let maxSegments = Number(enabled.maxSegments);
      let widthPx = Number(enabled.widthPx);
      let paddingPx = Number(enabled.paddingPx);
      let fontUi = Number(enabled.fontUi);
      let maxLineChars = Number(enabled.maxLineChars);
      let maxLinePx = Number(enabled.maxLinePx);
      let fitEpsilonPx = Number(enabled.fitEpsilonPx);
      let fallbackLines = null;
      let fallbackChars = null;
      let fallbackSegments = null;
      let fallbackWidth = null;
      let fallbackPadding = null;
      let fallbackFont = null;
      if (box === "mic" || box === "desktop") {
        const cfgWidth = readOverlayBoxConfigNumber(box, "width");
        const cfgPadding = readOverlayBoxConfigNumber(box, "padding");
        const cfgFont = readOverlayBoxConfigNumber(box, "fontSize");
        const cfgLines = readOverlayBoxConfigNumber(box, "maxSegments");
        const cfgChars = readOverlayBoxConfigNumber(box, "maxChars");
        if (cfgWidth !== null) fallbackWidth = cfgWidth;
        if (cfgPadding !== null) fallbackPadding = cfgPadding;
        if (cfgFont !== null) fallbackFont = cfgFont;
        if (cfgLines !== null) {
          fallbackLines = cfgLines;
          fallbackSegments = cfgLines;
        }
        if (cfgChars !== null) fallbackChars = cfgChars;
      }

      const merged = overlayConstraintsAuthority.mergeRuntimeLaneConstraint({
        incoming: {
          linesLimit,
          maxChars,
          maxSegments,
          widthPx,
          paddingPx,
          fontUi,
          maxLineChars,
          maxLinePx,
          fitEpsilonPx,
          noWordSplit: enabled.noWordSplit !== false,
        },
        fallback: {
          linesLimit: fallbackLines,
          maxChars: fallbackChars,
          maxSegments: fallbackSegments,
          widthPx: fallbackWidth,
          paddingPx: fallbackPadding,
          fontUi: fallbackFont,
          noWordSplit: enabled.noWordSplit !== false,
        },
        debugRaw: {
          width: payloadDbgRawWidth,
          font: payloadDbgRawFont,
          padding: payloadDbgRawPadding,
        },
      });
      linesLimit = merged.linesLimit;
      maxChars = merged.maxChars;
      maxSegments = merged.maxSegments;
      widthPx = merged.widthPx;
      paddingPx = merged.paddingPx;
      fontUi = merged.fontUi;
      if (Number.isFinite(Number(merged.maxLineChars))) {
        maxLineChars = Number(merged.maxLineChars);
      } else {
        maxLineChars = NaN;
      }
      if (Number.isFinite(Number(merged.maxLinePx))) {
        maxLinePx = Number(merged.maxLinePx);
      } else {
        maxLinePx = NaN;
      }
      if (Number.isFinite(Number(merged.fitEpsilonPx))) {
        fitEpsilonPx = Number(merged.fitEpsilonPx);
      } else {
        fitEpsilonPx = NaN;
      }
      const hasConstraints = Number.isFinite(linesLimit) || Number.isFinite(maxChars) || Number.isFinite(maxSegments)
        || Number.isFinite(widthPx) || Number.isFinite(paddingPx) || Number.isFinite(fontUi)
        || Number.isFinite(maxLineChars) || Number.isFinite(maxLinePx) || Number.isFinite(fitEpsilonPx);
      if (hasConstraints) {
        setOverlayTestStreamEnabled({
          enabled: coerceEnabled(enabled.enabled),
          box,
          linesLimit,
          maxChars,
          maxSegments,
          widthPx,
          paddingPx,
          fontUi,
          maxLineChars,
          maxLinePx,
          fitEpsilonPx,
          noWordSplit: enabled.noWordSplit !== false,
          authorityTrace: merged && merged.authorityTrace ? { ...merged.authorityTrace } : null,
        });
      } else {
        setOverlayTestStreamEnabled(coerceEnabled(enabled.enabled));
      }
    } else {
      setOverlayTestStreamEnabled(coerceEnabled(enabled));
    }
    // eslint-disable-next-line no-console
    console.log(
      `what_gui: ipc set-test-stream enabled=${getOverlayTestStreamEnabled()} ` +
      `has_payload=${payload ? "yes" : "no"} box='${payloadBox}' ` +
      `lines=${Number.isFinite(payloadLines) ? payloadLines : -1} ` +
      `chars=${Number.isFinite(payloadMaxChars) ? payloadMaxChars : -1} ` +
      `segments=${Number.isFinite(payloadMaxSegments) ? payloadMaxSegments : -1} ` +
      `w=${Number.isFinite(payloadWidth) ? payloadWidth : -1} ` +
      `pad=${Number.isFinite(payloadPadding) ? payloadPadding : -1} ` +
      `font=${Number.isFinite(payloadFont) ? payloadFont : -1} ` +
      `max_line=${Number.isFinite(payloadMaxLine) ? payloadMaxLine : -1} ` +
      `max_line_px=${Number.isFinite(payloadMaxLinePx) ? payloadMaxLinePx : -1} ` +
      `fit_eps=${Number.isFinite(payloadFitEpsilonPx) ? payloadFitEpsilonPx : -1} ` +
      `no_word_split=${payloadNoWordSplit ? "true" : "false"} ` +
      `raw_w='${payloadDbgRawWidth}' raw_font='${payloadDbgRawFont}' raw_pad='${payloadDbgRawPadding}' ` +
      `raw_seg='${payloadDbgRawSeg}' raw_chars='${payloadDbgRawChars}'`
    );
    const mainWindow = getMainWindow();
    if (mainWindow && !mainWindow.isDestroyed()) {
      const outbound = payload && typeof payload === "object"
        ? {
            ...payload,
            enabled: getOverlayTestStreamEnabled(),
          }
        : {
            enabled: getOverlayTestStreamEnabled(),
          };
      mainWindow.webContents.send("external-test-stream", outbound);
    }
    return { ok: true, enabled: getOverlayTestStreamEnabled() };
  });
}

module.exports = {
  registerOverlayIpcHandlers
};
