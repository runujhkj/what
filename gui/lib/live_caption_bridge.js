(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.whatGuiLiveCaptionBridge = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function createLiveCaptionBridge({ send, onEvent, onError, getDelaySeconds,
    setTimeoutFn = setTimeout, clearTimeoutFn = clearTimeout }) {
    let active = false;
    let seq = 0;
    let epoch = "";
    let chunkId = 0;
    let buffers = { mic: "", desktop: "" };
    let lanes = { mic: [], desktop: [] };
    const timers = new Set();

    function deliver(payload) {
      // Surface publication errors without interrupting transcript ingestion.
      try {
        Promise.resolve(send(payload)).then((result) => {
          if (result && result.ok === false) onError(result.error || "publication failed");
        }).catch(onError);
      } catch (error) { onError(error); }
    }

    function publish(clear = false) {
      const boxes = {};
      for (const source of ["mic", "desktop"]) {
        const events = lanes[source];
        boxes[source] = {
          captionStream: { id: `${epoch}:${source}`, chunks: events.map(event => ({ id: event.captionChunkId, text: event.text })) },
          bodyOnly: true,
          text: events.map((event) => event.text.trim()).join(" "),
          segments: events.flatMap((event) => event.segments || []),
          header: source === "mic" ? "Mic" : "Desktop",
        };
      }
      deliver({ seq: ++seq, trace_id: `live-caption-${seq}`, clear, bodyOnly: true,
        text: [boxes.mic.text, boxes.desktop.text].filter(Boolean).join("\n"), boxes });
    }

    function reset() {
      epoch = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
      chunkId = 0;
      for (const timer of timers) clearTimeoutFn(timer);
      timers.clear();
      buffers = { mic: "", desktop: "" };
      lanes = { mic: [], desktop: [] };
      publish(true);
    }

    function ingest(chunk, source) {
      if (!active || !Object.hasOwn(buffers, source)) return;
      buffers[source] += String(chunk);
      const lines = buffers[source].split("\n");
      buffers[source] = lines.pop();
      // Bound malformed/no-newline log input without touching complete events.
      if (buffers[source].length > 1024 * 1024) buffers[source] = "";
      for (const line of lines) {
        const marker = line.indexOf("EVENT:");
        if (marker < 0) continue;
        let event;
        try { event = JSON.parse(line.slice(marker + 6)); } catch (_) { continue; }
        if (event?.type !== "segment" || typeof event.text !== "string" || !event.text.trim()) continue;
        onEvent(event, source);
        const emit = () => {
          lanes[source].push({ ...event, captionChunkId: ++chunkId });
          // A bounded caption window, independent of transcript history.
          lanes[source] = lanes[source].slice(-3);
          publish();
        };
        const delay = Math.max(0, Math.min(90, Number(getDelaySeconds()) || 0)) * 1000;
        if (!delay) emit();
        else {
          const timer = setTimeoutFn(() => { timers.delete(timer); if (active) emit(); }, delay);
          timers.add(timer);
        }
      }
    }

    return {
      start() { active = true; reset(); },
      stop() { active = false; reset(); },
      ingest,
    };
  }
  return { createLiveCaptionBridge };
});
