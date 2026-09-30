(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.whatGuiOutputWatch = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  // Watches the default output device while a session starts, without delaying startup.
  // Session steps are marked as they happen; background polls compare the output device
  // with the one before Start and attribute a change to the most recent step. The device
  // behind a microphone opens shortly after its client starts, so the elapsed time since
  // that step is reported too.
  function createOutputWatch({
    read, onChange, now = () => Date.now(),
    setTimeoutFn = setTimeout, clearTimeoutFn = clearTimeout,
    intervalMs = 700, windowMs = 10000,
  }) {
    let run = 0;
    let timer = null;

    function stop() {
      run += 1;
      if (timer !== null) clearTimeoutFn(timer);
      timer = null;
    }

    async function start() {
      stop();
      const id = run;
      const steps = [];
      const startedAt = now();
      const before = await read();
      if (id !== run || !before || !before.ok || !before.output) return { mark() {} };
      let last = before.output;

      async function poll() {
        timer = null;
        if (id !== run) return;
        const cur = await read();
        if (id !== run) return;
        if (cur && cur.ok && cur.output && cur.output.name !== last.name) {
          const at = now();
          const step = steps.filter((s) => s.at <= at).pop() || null;
          onChange({
            from: last,
            to: cur.output,
            input: cur.input || null,
            step: step ? step.label : "before capture started",
            msAfterStep: step ? at - step.at : at - startedAt,
          });
          last = cur.output;
        }
        if (now() - startedAt < windowMs) timer = setTimeoutFn(poll, intervalMs);
      }

      timer = setTimeoutFn(poll, intervalMs);
      return {
        mark(label) {
          if (id === run) steps.push({ label: String(label), at: now() });
        },
      };
    }

    return { start, stop };
  }

  function describeOutputChange(change) {
    const dev = (d) => (d ? `${d.name} (${d.transport})` : "unknown");
    const secs = (Math.max(0, change.msAfterStep) / 1000).toFixed(1);
    const input = change.input ? ` Default input: ${dev(change.input)}.` : "";
    return `Output device changed from ${dev(change.from)} to ${dev(change.to)}, ${secs}s after ${change.step}. ` +
      `macOS moved system output; switch it back in Sound settings.${input}`;
  }

  return { createOutputWatch, describeOutputChange };
});
