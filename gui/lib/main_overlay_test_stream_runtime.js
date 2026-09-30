const lanePolicyRuntime = require("./test_stream_lane_policy");
const lanePipelineRuntime = require("./test_stream_lane_pipeline");

function normalizePayloadInput(payload) {
  return payload && typeof payload === "object" ? payload : {};
}

function traceIdFromPayload(payload) {
  const normalized = normalizePayloadInput(payload);
  return String(normalized.trace_id || "");
}

function isLocalTestPayload(payload) {
  return traceIdFromPayload(payload).startsWith("main-test-");
}

function isOverlayPayloadEffectivelyEmpty(payload) {
  const p = normalizePayloadInput(payload);
  const rootLines = Array.isArray(p.lines) ? p.lines.length : 0;
  const micLines = Array.isArray(p.boxes && p.boxes.mic && p.boxes.mic.lines) ? p.boxes.mic.lines.length : 0;
  const deskLines = Array.isArray(p.boxes && p.boxes.desktop && p.boxes.desktop.lines) ? p.boxes.desktop.lines.length : 0;
  return rootLines === 0 && micLines === 0 && deskLines === 0;
}

function shouldAcceptIncomingOverlayPayload(input) {
  const ctx = input && typeof input === "object" ? input : {};
  const enabled = Boolean(ctx.localTestStreamEnabled);
  const payload = normalizePayloadInput(ctx.payload);
  if (!enabled) return { accept: true, reason: "test_stream_off" };
  if (isLocalTestPayload(payload)) return { accept: true, reason: "local_test_payload" };
  if (isOverlayPayloadEffectivelyEmpty(payload)) return { accept: false, reason: "empty_while_test_stream_on" };
  return { accept: false, reason: "non_test_payload_while_test_stream_on" };
}

function createLocalTestStreamRuntime(input) {
  const ctx = input && typeof input === "object" ? input : {};
  const normalizeOverlayPayload = typeof ctx.normalizeOverlayPayload === "function"
    ? ctx.normalizeOverlayPayload
    : (value) => value;
  const onPayload = typeof ctx.onPayload === "function" ? ctx.onPayload : () => {};
  const onStateChange = typeof ctx.onStateChange === "function" ? ctx.onStateChange : () => {};
  const setIntervalFn = typeof ctx.setIntervalFn === "function" ? ctx.setIntervalFn : setInterval;
  const clearIntervalFn = typeof ctx.clearIntervalFn === "function" ? ctx.clearIntervalFn : clearInterval;
  const intervalMs = Math.max(50, Number(ctx.intervalMs) || 500);
  const defaultLinesLimit = Math.max(1, Math.min(10, Number(ctx.linesLimit) || 3));
  const defaultMaxChars = Math.max(20, Number(ctx.maxChars) || 280);

  function deriveMaxLineChars(maxChars, linesLimit) {
    const chars = Math.max(20, Number(maxChars) || defaultMaxChars);
    const lines = Math.max(1, Math.min(10, Number(linesLimit) || defaultLinesLimit));
    // Conservative cap to reduce OBS-side reflow/jitter when FT2 metrics differ at render time.
    return Math.max(16, Math.min(120, Math.floor(chars / (lines * 3))));
  }

  let enabled = false;
  let timer = null;
  let counter = 0;
  const lanePolicy = lanePolicyRuntime.createTestStreamLanePolicy({
    linesLimit: defaultLinesLimit,
    maxChars: defaultMaxChars,
    deriveMaxLineChars,
    usePixelFit: ctx.usePixelFit === true,
  });

  function normalizeBoxKey(value) {
    const key = String(value || "").trim().toLowerCase();
    if (key === "mic" || key === "desktop") return key;
    return "";
  }

  function resetState() {
    counter = 0;
    lanePolicy.reset();
  }

  function buildPayloadForCurrentCounter() {
    const sample = `test segment ${counter}`;
    return lanePipelineRuntime.buildTickPayload({
      counter,
      sample,
      lanePolicy,
      defaultLinesLimit,
      normalizeOverlayPayload,
    });
  }

  function tick() {
    if (!enabled) return null;
    counter += 1;
    const payload = buildPayloadForCurrentCounter();
    const state = getState();
    onPayload(payload, {
      counter,
      laneLines: {
        mic: lanePolicy.laneLines("mic"),
        desktop: lanePolicy.laneLines("desktop"),
      },
      constraints: state.constraints,
    });
    return payload;
  }

  function stopTimer() {
    if (!timer) return;
    clearIntervalFn(timer);
    timer = null;
  }

  function setEnabled(next, box) {
    const value = Boolean(next);
    const boxKey = normalizeBoxKey(box);
    lanePolicy.setEnabled(value, boxKey || "");
    const boxEnabled = {
      mic: lanePolicy.laneEnabled("mic"),
      desktop: lanePolicy.laneEnabled("desktop"),
    };
    const nextEnabled = boxEnabled.mic || boxEnabled.desktop;
    if (nextEnabled === enabled) return enabled;
    enabled = nextEnabled;
    stopTimer();
    if (enabled) {
      resetState();
      timer = setIntervalFn(tick, intervalMs);
    }
    onStateChange(enabled);
    return enabled;
  }

  function setConstraints(next) {
    const src = next && typeof next === "object" ? next : {};
    lanePolicy.setConstraints(src);
    return {
      mic: lanePolicy.laneConstraints("mic"),
      desktop: lanePolicy.laneConstraints("desktop"),
    };
  }

  function getState() {
    const boxEnabled = {
      mic: lanePolicy.laneEnabled("mic"),
      desktop: lanePolicy.laneEnabled("desktop"),
    };
    return {
      enabled,
      counter,
      constraints: {
        mic: lanePolicy.laneConstraints("mic"),
        desktop: lanePolicy.laneConstraints("desktop"),
      },
      boxEnabled: { ...boxEnabled },
      micLines: lanePolicy.laneLines("mic"),
      desktopLines: lanePolicy.laneLines("desktop"),
    };
  }

  return {
    setEnabled,
    setConstraints,
    isEnabled: () => enabled,
    stop: () => setEnabled(false),
    tick,
    getState,
  };
}

module.exports = {
  createLocalTestStreamRuntime,
  isLocalTestPayload,
  isOverlayPayloadEffectivelyEmpty,
  shouldAcceptIncomingOverlayPayload,
};
