const DEFAULT_OVERLAY_BOX = "default";
const OVERLAY_BOX_KEYS = new Set([DEFAULT_OVERLAY_BOX, "mic", "desktop"]);
const _RESERVED_BOX_KEYS = new Set(["", "all", "combined", "default"]);
const _registeredBoxKeys = new Set(["mic", "desktop"]);

function registerBoxKey(key) {
  const k = String(key || "").trim().toLowerCase();
  if (!k || _RESERVED_BOX_KEYS.has(k)) return false;
  _registeredBoxKeys.add(k);
  return true;
}

function registeredBoxKeys() {
  return Array.from(_registeredBoxKeys);
}

function createInitialOverlayPayload() {
  return {
    text: "",
    lines: [],
    segments: [],
    segmentSpans: [],
    transition: "none",
    enterLine: "",
    animationMode: "none",
    header: "",
    width: "",
    height: "",
    fontSize: "",
    padding: "",
    textColor: "",
    bgColor: "",
    noWordSplit: true,
    boxes: {}
  };
}

function normalizeOverlayBoxKey(raw) {
  const key = String(raw || "").trim().toLowerCase();
  if (!key || _RESERVED_BOX_KEYS.has(key)) return DEFAULT_OVERLAY_BOX;
  if (_registeredBoxKeys.has(key)) return key;
  return DEFAULT_OVERLAY_BOX;
}

function overlayPayloadForBox(payload, boxKey) {
  const key = normalizeOverlayBoxKey(boxKey);
  if (key === DEFAULT_OVERLAY_BOX) return payload;
  const box = payload && payload.boxes && payload.boxes[key];
  if (!box || typeof box !== "object") return payload;
  const merged = { ...payload, ...box };
  const rootSeq = Number(payload && payload.seq);
  const mergedSeq = Number(merged.seq);
  const resolvedSeq = Number.isFinite(mergedSeq)
    ? mergedSeq
    : (Number.isFinite(rootSeq) ? rootSeq : -1);
  const rootTrace = String((payload && payload.trace_id) ?? "");
  const mergedTrace = String(merged.trace_id ?? "");
  const resolvedTrace = mergedTrace || rootTrace;
  return {
    ...(merged.captionStream ? { captionStream: merged.captionStream } : {}),
    seq: resolvedSeq,
    trace_id: resolvedTrace,
    text: String(merged.text ?? ""),
    fullText: String(merged.fullText ?? merged.text ?? ""),
    lines: Array.isArray(merged.lines) ? merged.lines : [],
    segments: Array.isArray(merged.segments) ? merged.segments : [],
    segmentSpans: Array.isArray(merged.segmentSpans) ? merged.segmentSpans : [],
    transition: String(merged.transition ?? "none"),
    enterLine: String(merged.enterLine ?? ""),
    animationMode: String(merged.animationMode ?? "none"),
    header: String(merged.header ?? ""),
    width: String(merged.width ?? ""),
    height: String(merged.height ?? ""),
    fontSize: String(merged.fontSize ?? ""),
    padding: String(merged.padding ?? ""),
    textColor: String(merged.textColor ?? ""),
    bgColor: String(merged.bgColor ?? ""),
    noWordSplit: merged.noWordSplit !== false,
    box: key
  };
}

module.exports = {
  DEFAULT_OVERLAY_BOX,
  createInitialOverlayPayload,
  normalizeOverlayBoxKey,
  overlayPayloadForBox,
  registerBoxKey,
  registeredBoxKeys,
};
