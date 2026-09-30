function normalizeBoxEnabled(input) {
  const src = input && typeof input === "object" ? input : {};
  return {
    mic: Boolean(src.mic),
    desktop: Boolean(src.desktop),
  };
}

function pickLaneForCounter(input) {
  const ctx = input && typeof input === "object" ? input : {};
  const counter = Number(ctx.counter) || 0;
  const boxEnabled = normalizeBoxEnabled(ctx.boxEnabled);
  const activeLanes = ["mic", "desktop"].filter((key) => boxEnabled[key]);
  if (activeLanes.length === 1) return activeLanes[0];
  if (!activeLanes.length) return "mic";
  return counter % 2 === 0 ? "desktop" : "mic";
}

function interleaveLaneLines(input) {
  const ctx = input && typeof input === "object" ? input : {};
  const micLines = Array.isArray(ctx.micLines) ? ctx.micLines : [];
  const desktopLines = Array.isArray(ctx.desktopLines) ? ctx.desktopLines : [];
  const merged = [];
  const maxLen = Math.max(micLines.length, desktopLines.length);
  for (let i = 0; i < maxLen; i += 1) {
    if (micLines[i]) merged.push(String(micLines[i]));
    if (desktopLines[i]) merged.push(String(desktopLines[i]));
  }
  return merged;
}

function computeRootLinesLimit(input) {
  const ctx = input && typeof input === "object" ? input : {};
  const fallback = Math.max(1, Number(ctx.fallbackLimit) || 1);
  const micLimit = Math.max(1, Number(ctx.micConstraints && ctx.micConstraints.linesLimit) || fallback);
  const desktopLimit = Math.max(1, Number(ctx.desktopConstraints && ctx.desktopConstraints.linesLimit) || fallback);
  return Math.max(micLimit, desktopLimit);
}

function laneGeometry(constraints) {
  const c = constraints && typeof constraints === "object" ? constraints : {};
  const width = Math.max(100, Number(c.widthPx) || 640);
  const padding = Math.max(0, Number(c.paddingPx) || 6);
  const fontUi = Math.max(0.1, Number(c.fontUi) || 3);
  return {
    width: String(width),
    padding: String(padding),
    fontSize: String(fontUi),
  };
}

function buildTickPayload(input) {
  const ctx = input && typeof input === "object" ? input : {};
  const counter = Number(ctx.counter) || 0;
  const sample = String(ctx.sample || "");
  const fallbackLimit = Math.max(1, Number(ctx.defaultLinesLimit) || 3);
  const normalizeOverlayPayload = typeof ctx.normalizeOverlayPayload === "function"
    ? ctx.normalizeOverlayPayload
    : (value) => value;
  const lanePolicy = ctx.lanePolicy;

  const boxEnabled = {
    mic: lanePolicy && typeof lanePolicy.laneEnabled === "function" ? lanePolicy.laneEnabled("mic") : false,
    desktop: lanePolicy && typeof lanePolicy.laneEnabled === "function" ? lanePolicy.laneEnabled("desktop") : false,
  };
  const lane = pickLaneForCounter({ counter, boxEnabled });
  if (lanePolicy && typeof lanePolicy.append === "function") {
    lanePolicy.append(lane, sample, { segmentId: counter });
  }

  const micLines = lanePolicy && typeof lanePolicy.laneLines === "function" ? lanePolicy.laneLines("mic") : [];
  const desktopLines = lanePolicy && typeof lanePolicy.laneLines === "function" ? lanePolicy.laneLines("desktop") : [];
  const micConstraints = lanePolicy && typeof lanePolicy.laneConstraints === "function"
    ? lanePolicy.laneConstraints("mic")
    : { linesLimit: fallbackLimit };
  const desktopConstraints = lanePolicy && typeof lanePolicy.laneConstraints === "function"
    ? lanePolicy.laneConstraints("desktop")
    : { linesLimit: fallbackLimit };
  const merged = interleaveLaneLines({ micLines, desktopLines });
  const rootLinesLimit = computeRootLinesLimit({
    micConstraints,
    desktopConstraints,
    fallbackLimit,
  });
  const rootLines = merged.slice(-rootLinesLimit);
  const micFlow = micLines.join("\n").trim();
  const desktopFlow = desktopLines.join("\n").trim();
  const rootFlow = rootLines.join("\n").trim();
  const micGeom = laneGeometry(micConstraints);
  const deskGeom = laneGeometry(desktopConstraints);

  return normalizeOverlayPayload(overlayPayloadWriter.buildOverlayPayload({
    seq: counter,
    traceId: `main-test-${counter}`,
    rootText: rootFlow,
    rootFullText: rootFlow,
    rootLines,
    transition: "none",
    enterLine: "",
    animationMode: "none",
    rootConfig: {
      header: "",
      widthPx: micGeom.width,
      paddingPx: micGeom.padding,
      fontUi: micGeom.fontSize,
    },
    micText: micFlow,
    micFullText: micFlow,
    micLines,
    micTransition: "none",
    micEnterLine: "",
    micConfig: {
      header: "",
      widthPx: micGeom.width,
      paddingPx: micGeom.padding,
      fontUi: micGeom.fontSize,
    },
    desktopText: desktopFlow,
    desktopFullText: desktopFlow,
    desktopLines,
    desktopTransition: "none",
    desktopEnterLine: "",
    desktopConfig: {
      header: "",
      widthPx: deskGeom.width,
      paddingPx: deskGeom.padding,
      fontUi: deskGeom.fontSize,
    },
  }));
}

module.exports = {
  pickLaneForCounter,
  interleaveLaneLines,
  computeRootLinesLimit,
  laneGeometry,
  buildTickPayload,
};
const overlayPayloadWriter = require("./overlay_payload_writer");
