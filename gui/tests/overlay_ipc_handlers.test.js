const assert = require("assert");
const { registerOverlayIpcHandlers } = require("../lib/overlay_ipc_handlers");

  function makeHarness() {
  const handlers = new Map();
  const ipcMain = {
    handle(name, fn) {
      handlers.set(name, fn);
    }
  };
  let overlayPayload = { text: "", boxes: {} };
  let overlayTestStreamEnabled = false;
  let lastSetTestStreamArg = null;
  const writes = [];
  const overlayClients = new Map();
  overlayClients.set({ write: (line) => writes.push(["default", line]) }, "default");
  overlayClients.set({ write: (line) => writes.push(["desktop", line]) }, "desktop");

  const mainWindowEvents = [];
  const mainWindow = {
    isDestroyed() {
      return false;
    },
    webContents: {
      send(channel, value) {
        mainWindowEvents.push([channel, value]);
      }
    }
  };

  registerOverlayIpcHandlers({
    ipcMain,
    normalizeOverlayPayload(payload) {
      return payload && typeof payload === "object" ? payload : {};
    },
    getOverlayPayload() {
      return overlayPayload;
    },
    setOverlayPayload(next) {
      overlayPayload = next;
    },
    overlayClients,
    overlayPayloadForBox(boxKey, payload) {
      if (boxKey === "desktop" && payload.boxes && payload.boxes.desktop) {
        return { ...payload, ...payload.boxes.desktop, box: "desktop" };
      }
      return payload;
    },
    encodeOverlay(payload) {
      return JSON.stringify(payload);
    },
    getOverlayPort() {
      return 8790;
    },
    getMainWindow() {
      return mainWindow;
    },
    getOverlayTestStreamEnabled() {
      return overlayTestStreamEnabled;
    },
    setOverlayTestStreamEnabled(enabled) {
      lastSetTestStreamArg = enabled;
      if (enabled && typeof enabled === "object") {
        overlayTestStreamEnabled = Boolean(enabled.enabled);
      } else {
        overlayTestStreamEnabled = Boolean(enabled);
      }
    }
  });

  return {
    handlers,
    writes,
    mainWindowEvents,
    getLastSetTestStreamArg: () => lastSetTestStreamArg,
    getOverlayPayload: () => overlayPayload,
  };
}

async function testOverlayHandlersContract() {
  const h = makeHarness();
  ["set-overlay-text", "get-overlay-url", "set-test-stream"].forEach((name) => {
    assert.ok(h.handlers.has(name), `missing handler ${name}`);
  });

  const setOut = await h.handlers.get("set-overlay-text")(null, {
    text: "root",
    boxes: { desktop: { text: "desk" } }
  });
  assert.strictEqual(setOut.ok, true);
  assert.strictEqual(setOut.url, "http://127.0.0.1:8790/overlay");
  assert.strictEqual(h.writes.length, 2);
  assert.ok(h.writes[0][1].includes('"text":"root"'));
  assert.ok(h.writes[1][1].includes('"text":"desk"'));

  await h.handlers.get("set-overlay-text")(null, {
    seq: 2,
    trace_id: "ovl-2",
    text: "",
    lines: [],
    boxes: {
      mic: { text: "alpha beta", lines: ["alpha beta"] },
    },
  });
  await h.handlers.get("set-overlay-text")(null, {
    seq: 3,
    trace_id: "ovl-3",
    text: "",
    lines: [],
    boxes: {
      mic: { text: "", lines: [] },
    },
  });
  const continuityPayload = h.getOverlayPayload();
  assert.ok(continuityPayload && continuityPayload.boxes && continuityPayload.boxes.mic);
  assert.deepStrictEqual(continuityPayload.boxes.mic.lines, ["alpha beta"]);
  assert.strictEqual(continuityPayload.boxes.mic.text, "alpha beta");

  const urls = await h.handlers.get("get-overlay-url")();
  assert.strictEqual(urls.ok, true);
  assert.strictEqual(urls.url, "http://127.0.0.1:8790/overlay");
  assert.strictEqual(urls.events_url, "http://127.0.0.1:8790/events");
  assert.strictEqual(urls.mic_url, "http://127.0.0.1:8790/events?box=mic");
  assert.strictEqual(urls.desktop_url, "http://127.0.0.1:8790/events?box=desktop");

  const toggled = await h.handlers.get("set-test-stream")(null, true);
  assert.deepStrictEqual(toggled, { ok: true, enabled: true });
  assert.deepStrictEqual(h.mainWindowEvents, [["external-test-stream", { enabled: true }]]);

  const toggledObj = await h.handlers.get("set-test-stream")(null, {
    enabled: "false",
    box: "desktop",
    linesLimit: 6,
    maxChars: 280,
  });
  assert.deepStrictEqual(toggledObj, { ok: true, enabled: false });

  await h.handlers.get("set-overlay-text")(null, {
    text: "",
    boxes: {
      mic: { config: { width: "870", padding: "4", fontSize: "5.9", maxSegments: "7", maxChars: "280" } },
      desktop: { config: { width: "510", padding: "6", fontSize: "11.15", maxSegments: "3", maxChars: "280" } },
    },
  });
  await h.handlers.get("set-test-stream")(null, {
    enabled: true,
    box: "mic",
    linesLimit: 3,
    maxChars: 280,
    maxSegments: 3,
    widthPx: 510,
    paddingPx: 6,
    fontUi: 5.9,
    maxLineChars: 46,
    _debug_box_raw_width: "",
    _debug_box_raw_font: "",
    _debug_box_raw_padding: "",
  });
  const merged = h.getLastSetTestStreamArg();
  assert.ok(merged && typeof merged === "object");
  assert.strictEqual(merged.box, "mic");
  assert.strictEqual(merged.widthPx, 510);
  assert.strictEqual(merged.paddingPx, 6);
  assert.strictEqual(merged.maxSegments, 3);
  assert.strictEqual(merged.linesLimit, 3);
  assert.strictEqual(Number.isFinite(Number(merged.maxLineChars)), false);
  assert.ok(merged.authorityTrace && typeof merged.authorityTrace === "object");
  assert.strictEqual(merged.authorityTrace.preferFallbackGeometry, true);
  assert.strictEqual(merged.authorityTrace.widthPx, "incoming");
  assert.strictEqual(merged.authorityTrace.maxLineChars, "derived");

  await h.handlers.get("set-overlay-text")(null, {
    text: "",
    boxes: {
      mic: { config: { width: "", padding: "", fontSize: "", maxSegments: "", maxChars: "" } },
      desktop: { config: { width: "", padding: "", fontSize: "", maxSegments: "", maxChars: "" } },
    },
  });
  await h.handlers.get("set-test-stream")(null, {
    enabled: true,
    box: "mic",
    linesLimit: 3,
    maxChars: 280,
    maxSegments: 3,
    widthPx: 870,
    paddingPx: 6,
    fontUi: 5.9,
    _debug_box_raw_width: "",
    _debug_box_raw_font: "",
    _debug_box_raw_padding: "",
  });
  const mergedEmptyCfg = h.getLastSetTestStreamArg();
  assert.strictEqual(mergedEmptyCfg.linesLimit, 3);
  assert.strictEqual(mergedEmptyCfg.maxChars, 280);
  assert.strictEqual(mergedEmptyCfg.maxSegments, 3);
  assert.strictEqual(mergedEmptyCfg.widthPx, 870);
  assert.strictEqual(mergedEmptyCfg.fontUi, 5.9);
}

async function run() {
  await testOverlayHandlersContract();
  console.log("overlay_ipc_handlers.test.js: ok");
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
