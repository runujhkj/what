function createOverlayBroadcaster(input) {
  const ctx = input && typeof input === "object" ? input : {};
  const getOverlayPayload = typeof ctx.getOverlayPayload === "function"
    ? ctx.getOverlayPayload
    : () => ({});
  const overlayPayloadForBox = typeof ctx.overlayPayloadForBox === "function"
    ? ctx.overlayPayloadForBox
    : (_boxKey, payload) => payload;
  const overlayClients = ctx.overlayClients && typeof ctx.overlayClients.forEach === "function"
    ? ctx.overlayClients
    : new Map();
  const encodeOverlay = typeof ctx.encodeOverlay === "function"
    ? ctx.encodeOverlay
    : JSON.stringify;
  const log = typeof ctx.log === "function" ? ctx.log : () => {};

  function linesLength(payload, path) {
    const candidate = path(payload);
    return Array.isArray(candidate) ? candidate.length : 0;
  }

  function firstLine(payload, path) {
    const candidate = path(payload);
    return Array.isArray(candidate) ? String(candidate[0] || "") : "";
  }

  return function broadcastOverlayPayload() {
    const payload = getOverlayPayload();
    try {
      const rootLinesN = linesLength(payload, (p) => p && p.lines);
      const micLinesN = linesLength(payload, (p) => p && p.boxes && p.boxes.mic && p.boxes.mic.lines);
      const deskLinesN = linesLength(payload, (p) => p && p.boxes && p.boxes.desktop && p.boxes.desktop.lines);
      const micFirst = firstLine(payload, (p) => p && p.boxes && p.boxes.mic && p.boxes.mic.lines);
      const deskFirst = firstLine(payload, (p) => p && p.boxes && p.boxes.desktop && p.boxes.desktop.lines);
      const seq = Number(payload && payload.seq);
      const clientsN = typeof overlayClients.size === "number" ? overlayClients.size : -1;
      log(
        `what_gui: broadcast payload seq=${Number.isFinite(seq) ? seq : -1} ` +
        `trace='${String((payload && payload.trace_id) || "")}' root_l=${rootLinesN} ` +
        `mic_l=${micLinesN} desk_l=${deskLinesN} mic_first='${micFirst}' ` +
        `desk_first='${deskFirst}' clients=${clientsN}`
      );
    } catch (_err) {
      // ignore telemetry failures
    }

    overlayClients.forEach((boxKey, res) => {
      try {
        const scoped = overlayPayloadForBox(boxKey, payload);
        res.write(`data: ${encodeOverlay(scoped)}\n\n`);
      } catch (_err) {
        // ignore write failures
      }
    });
  };
}

module.exports = {
  createOverlayBroadcaster,
};
