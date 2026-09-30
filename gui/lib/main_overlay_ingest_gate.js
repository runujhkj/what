function createOverlayIngestGate(input) {
  const ctx = input && typeof input === "object" ? input : {};
  const shouldAcceptIncomingOverlayPayload = typeof ctx.shouldAcceptIncomingOverlayPayload === "function"
    ? ctx.shouldAcceptIncomingOverlayPayload
    : () => ({ accept: true, reason: "default_accept" });
  const isLocalTestStreamEnabled = typeof ctx.isLocalTestStreamEnabled === "function"
    ? ctx.isLocalTestStreamEnabled
    : () => false;
  const setOverlayPayload = typeof ctx.setOverlayPayload === "function"
    ? ctx.setOverlayPayload
    : () => {};
  const log = typeof ctx.log === "function" ? ctx.log : () => {};

  return function ingestOverlayPayload(next) {
    const policy = shouldAcceptIncomingOverlayPayload({
      localTestStreamEnabled: isLocalTestStreamEnabled(),
      payload: next,
    });
    if (!policy.accept) {
      const traceId = String((next && next.trace_id) || "");
      log(`what_gui: set-overlay-text ignored while local-test-stream enabled trace='${traceId}' reason=${policy.reason}`);
      return { accepted: false, reason: policy.reason };
    }
    log(`what_gui: set-overlay-text accepted while test_stream=${isLocalTestStreamEnabled() ? "on" : "off"}`);
    setOverlayPayload(next);
    return { accepted: true, reason: policy.reason || "accepted" };
  };
}

module.exports = {
  createOverlayIngestGate,
};
