(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory(require("./overlay_body_sanitizer"));
    return;
  }
  const sanitizer = root.whatGuiOverlayBodySanitizer || {};
  root.whatGuiOverlayPayloadContract = factory(sanitizer);
})(typeof globalThis !== "undefined" ? globalThis : this, function (sanitizer) {
  const sanitizeBody =
    sanitizer && typeof sanitizer.sanitizeBody === "function"
      ? sanitizer.sanitizeBody
      : function (linesIn, textIn) {
          const lines = Array.isArray(linesIn) ? linesIn.map((v) => String(v || "")) : String(textIn || "").split("\n");
          const cleaned = lines.map((v) => String(v || "").trim()).filter(Boolean);
          return { lines: cleaned, text: cleaned.join("\n").trim() };
        };

  function normalizeBodyForBox(box, labels) {
    const src = box && typeof box === "object" ? box : {};
    // Live transcript producers send labels separately; "Mic"/"Desktop" may be speech.
    const body = sanitizeBody(src.lines, src.text, src.bodyOnly === true ? [] : labels);
    const cfgSrc = src.config && typeof src.config === "object" ? src.config : {};
    const cfg = {
      maxSegments: Number.isFinite(Number(cfgSrc.maxSegments)) ? Number(cfgSrc.maxSegments) : 0,
      maxChars: Number.isFinite(Number(cfgSrc.maxChars)) ? Number(cfgSrc.maxChars) : 0,
      width: Number.isFinite(Number(cfgSrc.width)) ? Number(cfgSrc.width) : 0,
      height: Number.isFinite(Number(cfgSrc.height)) ? Number(cfgSrc.height) : 0,
      padding: Number.isFinite(Number(cfgSrc.padding)) ? Number(cfgSrc.padding) : 0,
      fontSize: Number.isFinite(Number(cfgSrc.fontSize)) ? Number(cfgSrc.fontSize) : 0,
    };
    return {
      ...(src.bodyOnly === true ? { bodyOnly: true } : {}),
      ...(src.captionStream && typeof src.captionStream.id === "string" && Array.isArray(src.captionStream.chunks)
        ? { captionStream: { id: src.captionStream.id, chunks: src.captionStream.chunks
          .filter(chunk => chunk && Number.isSafeInteger(chunk.id) && typeof chunk.text === "string")
          .map(chunk => ({ id: chunk.id, text: chunk.text })) } } : {}),
      seq: Number.isFinite(Number(src.seq)) ? Number(src.seq) : undefined,
      trace_id: String(src.trace_id ?? ""),
      text: body.text,
      fullText: String(src.fullText ?? body.text),
      lines: body.lines,
      segments: Array.isArray(src.segments) ? src.segments : [],
      segmentSpans: Array.isArray(src.segmentSpans) ? src.segmentSpans : [],
      transition: String(src.transition || "none"),
      enterLine: String(src.enterLine ?? ""),
      animationMode: String(src.animationMode || "none"),
      header: String(src.header ?? ""),
      width: String(src.width ?? ""),
      height: String(src.height ?? ""),
      fontSize: String(src.fontSize ?? ""),
      padding: String(src.padding ?? ""),
      textColor: String(src.textColor ?? ""),
      bgColor: String(src.bgColor ?? ""),
      noWordSplit: src.noWordSplit !== false,
      config: cfg,
    };
  }

  function normalizeOverlayPayload(payload) {
    const src = payload && typeof payload === "object" ? payload : {};
    const rootSeq = Number(src.seq);
    const rootTraceId = String(src.trace_id ?? "");
    const rootHeader = String(src.header ?? "");
    const rootBody = sanitizeBody(src.lines, src.text, src.bodyOnly === true ? [] : [rootHeader]);
    const boxesIn = src.boxes && typeof src.boxes === "object" ? src.boxes : {};
    const boxes = {};
    for (const key of Object.keys(boxesIn)) {
      const box = boxesIn[key];
      if (!box || typeof box !== "object") continue;
      const boxHeader = String(box.header ?? "");
      const displayName = key.charAt(0).toUpperCase() + key.slice(1);
      boxes[key] = normalizeBodyForBox(box, [boxHeader, key, displayName]);
    }
    return {
      ...(src.bodyOnly === true ? { bodyOnly: true } : {}),
      ...(src.captionStream && typeof src.captionStream.id === "string" && Array.isArray(src.captionStream.chunks)
        ? { captionStream: { id: src.captionStream.id, chunks: src.captionStream.chunks
          .filter(chunk => chunk && Number.isSafeInteger(chunk.id) && typeof chunk.text === "string")
          .map(chunk => ({ id: chunk.id, text: chunk.text })) } } : {}),
      seq: Number.isFinite(rootSeq) ? rootSeq : -1,
      trace_id: rootTraceId,
      text: rootBody.text,
      fullText: String(src.fullText ?? rootBody.text),
      lines: rootBody.lines,
      segments: Array.isArray(src.segments) ? src.segments : [],
      segmentSpans: Array.isArray(src.segmentSpans) ? src.segmentSpans : [],
      transition: String(src.transition || "none"),
      enterLine: String(src.enterLine ?? ""),
      animationMode: String(src.animationMode || "none"),
      header: rootHeader,
      width: String(src.width ?? ""),
      height: String(src.height ?? ""),
      fontSize: String(src.fontSize ?? ""),
      padding: String(src.padding ?? ""),
      textColor: String(src.textColor ?? ""),
      bgColor: String(src.bgColor ?? ""),
      noWordSplit: src.noWordSplit !== false,
      boxes,
    };
  }

  return {
    normalizeOverlayPayload,
  };
});
