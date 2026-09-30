"use strict";
const assert = require("node:assert/strict");
const { createOutputWatch, describeOutputChange } = require("../lib/output_watch");

const HEADSET = { name: "BT Headset", transport: "Bluetooth" };
const USB_ADAPTER = { name: "USB Audio Adapter", transport: "USB" };

function harness(sequence) {
  let t = 0;
  const timers = [];
  const changes = [];
  const reads = sequence.slice();
  const watch = createOutputWatch({
    read: async () => reads.length > 1 ? reads.shift() : reads[0],
    onChange: (c) => changes.push(c),
    now: () => t,
    setTimeoutFn: (fn, ms) => { timers.push({ fn, due: t + ms }); return timers.length; },
    clearTimeoutFn: () => { timers.length = 0; },
    intervalMs: 700,
    windowMs: 10000,
  });
  async function advance(ms) {
    t += ms;
    while (timers.length && timers[0].due <= t) await timers.shift().fn();
  }
  return { watch, changes, advance, setTime: (v) => { t = v; }, timers };
}

(async () => {
  // A change is attributed to the latest step before it was observed, with elapsed time.
  {
    const ok = (output) => ({ ok: true, output, input: HEADSET });
    const h = harness([ok(HEADSET), ok(HEADSET), ok(USB_ADAPTER), ok(USB_ADAPTER)]);
    const session = await h.watch.start();
    session.mark("starting the Whisper service");
    await h.advance(700); // HEADSET: unchanged
    session.mark("opening the microphone (System default input)");
    await h.advance(700); // USB Audio Adapter: changed 0.7s after the mic step
    assert.equal(h.changes.length, 1);
    assert.deepEqual(h.changes[0].from, HEADSET);
    assert.deepEqual(h.changes[0].to, USB_ADAPTER);
    assert.equal(h.changes[0].step, "opening the microphone (System default input)");
    assert.equal(h.changes[0].msAfterStep, 700);
    await h.advance(700);
    assert.equal(h.changes.length, 1); // reported once
    assert.equal(
      describeOutputChange(h.changes[0]),
      "Output device changed from BT Headset (Bluetooth) to USB Audio Adapter (USB), 0.7s after opening the microphone " +
      "(System default input). macOS moved system output; switch it back in Sound settings. " +
      "Default input: BT Headset (Bluetooth).",
    );
  }

  // Polling stops after the window; stop() cancels a session; failures are ignored.
  {
    const h = harness([{ ok: true, output: USB_ADAPTER }]);
    await h.watch.start();
    for (let i = 0; i < 20; i += 1) await h.advance(700);
    assert.equal(h.timers.length, 0);

    const h2 = harness([{ ok: true, output: USB_ADAPTER }, { ok: true, output: HEADSET }]);
    await h2.watch.start();
    h2.watch.stop();
    await h2.advance(700);
    assert.equal(h2.changes.length, 0);

    const h3 = harness([{ ok: false, error: "unsupported_platform" }]);
    const session = await h3.watch.start();
    session.mark("anything");
    assert.equal(h3.timers.length, 0);
  }
  console.log("output_watch tests passed");
})().catch((err) => { console.error(err); process.exit(1); });
