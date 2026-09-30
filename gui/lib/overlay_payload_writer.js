(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
    return;
  }
  root.whatGuiOverlayPayloadWriter = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function asString(value, fallback = "") {
    return String(value == null ? fallback : value);
  }

  function asBoolean(value, fallback = true) {
    if (value == null) return fallback;
    return Boolean(value);
  }

  function asFiniteNumber(value, fallback = -1) {
    const n = Number(value);
    return Number.isFinite(n) ? n : fallback;
  }

  function normalizeLines(lines) {
    return Array.isArray(lines) ? lines.map((line) => String(line || "")) : [];
  }

  function buildBoxPayload(input) {
    const ctx = input && typeof input === "object" ? input : {};
    const cfg = ctx.config && typeof ctx.config === "object" ? ctx.config : {};
    const lines = normalizeLines(ctx.lines);
    const text = asString(ctx.text, lines.join("\n"));
    return {
      seq: asFiniteNumber(ctx.seq, -1),
      trace_id: asString(ctx.traceId, ""),
      text,
      fullText: asString(ctx.fullText, text),
      lines,
      segments: Array.isArray(ctx.segments) ? ctx.segments : [],
      segmentSpans: Array.isArray(ctx.segmentSpans) ? ctx.segmentSpans : [],
      transition: asString(ctx.transition, "none"),
      enterLine: asString(ctx.enterLine, ""),
      animationMode: asString(ctx.animationMode, "none"),
      header: asString(cfg.header, ""),
      width: asString(cfg.widthPx, ""),
      height: asString(cfg.heightPx, ""),
      fontSize: asString(cfg.fontUi, ""),
      padding: asString(cfg.paddingPx, ""),
      textColor: cfg.textColor,
      bgColor: cfg.bgColor,
      noWordSplit: asBoolean(cfg.noWordSplit, true),
    };
  }

  function buildOverlayPayload(input) {
    const ctx = input && typeof input === "object" ? input : {};
    const rootCfg = ctx.rootConfig && typeof ctx.rootConfig === "object" ? ctx.rootConfig : {};
    const micCfg = ctx.micConfig && typeof ctx.micConfig === "object" ? ctx.micConfig : {};
    const desktopCfg = ctx.desktopConfig && typeof ctx.desktopConfig === "object" ? ctx.desktopConfig : {};
    const root = buildBoxPayload({
      seq: ctx.seq,
      traceId: ctx.traceId,
      text: ctx.rootText,
      fullText: ctx.rootFullText,
      lines: ctx.rootLines,
      segments: ctx.rootSegments,
      segmentSpans: ctx.rootSegmentSpans,
      transition: ctx.transition,
      enterLine: ctx.enterLine,
      animationMode: ctx.animationMode,
      config: rootCfg,
    });
    const mic = buildBoxPayload({
      seq: ctx.seq,
      traceId: ctx.traceId,
      text: ctx.micText,
      fullText: ctx.micFullText,
      lines: ctx.micLines,
      segments: ctx.micSegments,
      segmentSpans: ctx.micSegmentSpans,
      transition: ctx.micTransition,
      enterLine: ctx.micEnterLine,
      animationMode: ctx.animationMode,
      config: micCfg,
    });
    const desktop = buildBoxPayload({
      seq: ctx.seq,
      traceId: ctx.traceId,
      text: ctx.desktopText,
      fullText: ctx.desktopFullText,
      lines: ctx.desktopLines,
      segments: ctx.desktopSegments,
      segmentSpans: ctx.desktopSegmentSpans,
      transition: ctx.desktopTransition,
      enterLine: ctx.desktopEnterLine,
      animationMode: ctx.animationMode,
      config: desktopCfg,
    });
    return {
      seq: root.seq,
      trace_id: root.trace_id,
      text: root.text,
      fullText: root.fullText,
      lines: root.lines,
      segments: root.segments,
      segmentSpans: root.segmentSpans,
      transition: root.transition,
      enterLine: root.enterLine,
      animationMode: root.animationMode,
      header: root.header,
      width: root.width,
      height: root.height,
      fontSize: root.fontSize,
      padding: root.padding,
      textColor: root.textColor,
      bgColor: root.bgColor,
      noWordSplit: root.noWordSplit,
      boxes: {
        mic,
        desktop,
      }
    };
  }

  return {
    buildBoxPayload,
    buildOverlayPayload,
  };
});
