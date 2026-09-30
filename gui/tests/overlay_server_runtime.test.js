const assert = require("assert");
const { createOverlayServerRuntime } = require("../lib/overlay_server_runtime");

function makeHttpHarness() {
  const instances = [];
  const http = {
    createServer(handler) {
      const server = {
        handler,
        listeners: {},
        listenCalls: [],
        closeCalls: 0,
        on(name, fn) {
          this.listeners[name] = fn;
        },
        listen(port) {
          this.listenCalls.push(port);
        },
        close() {
          this.closeCalls += 1;
        }
      };
      instances.push(server);
      return server;
    }
  };
  return { http, instances };
}

function makeReq(url, method = "GET") {
  const listeners = {};
  return {
    url,
    method,
    on(name, fn) {
      listeners[name] = fn;
    },
    emit(name, data) {
      if (listeners[name]) listeners[name](data);
    }
  };
}

function makeRes() {
  return {
    status: null,
    headers: null,
    body: "",
    writes: [],
    ended: false,
    writeHead(status, headers) {
      this.status = status;
      this.headers = headers;
    },
    write(chunk) {
      this.writes.push(String(chunk));
    },
    end(chunk = "") {
      this.ended = true;
      this.body += String(chunk);
    }
  };
}

function buildRuntime(overrides = {}) {
  const { http, instances } = makeHttpHarness();
  const overlayClients = new Map();
  let overlayTestStreamEnabled = false;
  const toggleCalls = [];
  const notifications = [];
  const timers = [];
  const runtime = createOverlayServerRuntime({
    http,
    normalizeOverlayBoxKey(raw) {
      const k = String(raw || "").trim().toLowerCase();
      if (!k || k === "default" || k === "all" || k === "combined") return "default";
      if (k === "mic" || k === "desktop") return k;
      return "default";
    },
    encodeOverlay(payload) {
      return JSON.stringify(payload);
    },
    overlayPayloadForBox(boxKey) {
      if (boxKey === "desktop") return { text: "desktop" };
      return { text: "root" };
    },
    overlayClients,
    getOverlayTestStreamEnabled() {
      return overlayTestStreamEnabled;
    },
    setOverlayTestStreamEnabled(enabled) {
      toggleCalls.push(enabled);
      if (enabled && typeof enabled === "object") {
        overlayTestStreamEnabled = Boolean(enabled.enabled);
      } else {
        overlayTestStreamEnabled = Boolean(enabled);
      }
    },
    notifyExternalTestStream(enabled) {
      notifications.push(enabled);
    },
    overlayBasePort: 8790,
    setTimeoutFn(fn, ms) {
      timers.push([fn, ms]);
    },
    logError() {},
    ...overrides
  });
  return { runtime, instances, overlayClients, notifications, timers, toggleCalls };
}

function testRoutesAndSseLifecycle() {
  const h = buildRuntime();
  h.runtime.start();
  assert.strictEqual(h.instances.length, 1);
  assert.deepStrictEqual(h.instances[0].listenCalls, [8790]);

  const overlayReq = makeReq("/overlay?box=desktop&header=Desk");
  const overlayRes = makeRes();
  h.instances[0].handler(overlayReq, overlayRes);
  assert.strictEqual(overlayRes.status, 200);
  assert.ok(String(overlayRes.headers["Content-Type"]).includes("text/html"));
  assert.ok(overlayRes.body.includes("<!doctype html>"));
  assert.ok(overlayRes.body.includes('<div id="frame">'));
  assert.ok(overlayRes.body.includes('<div id="header"></div>'));
  assert.ok(overlayRes.body.includes('<div id="box">'));
  assert.ok(overlayRes.body.indexOf('<div id="header"></div>') < overlayRes.body.indexOf('<div id="box">'));

  for (const route of ["/caption-box?box=mic", "/caption-box-settings"]) {
    const res = makeRes();
    h.instances[0].handler(makeReq(route), res);
    assert.strictEqual(res.status, 200);
    assert.ok(res.body.includes("What caption box") || res.body.includes("Caption box prototype"));
  }

  const eventsReq = makeReq("/events?box=desktop");
  const eventsRes = makeRes();
  h.instances[0].handler(eventsReq, eventsRes);
  assert.strictEqual(eventsRes.status, 200);
  assert.ok(eventsRes.writes.join("").includes('"text":"desktop"'));
  assert.strictEqual(h.overlayClients.size, 1);
  eventsReq.emit("close");
  assert.strictEqual(h.overlayClients.size, 0);

  const getReq = makeReq("/test-stream", "GET");
  const getRes = makeRes();
  h.instances[0].handler(getReq, getRes);
  assert.strictEqual(getRes.status, 200);
  assert.ok(getRes.body.includes('"enabled":false'));

  const postReq = makeReq("/test-stream", "POST");
  const postRes = makeRes();
  h.instances[0].handler(postReq, postRes);
  postReq.emit("data", '{"enabled":true}');
  postReq.emit("end");
  assert.strictEqual(postRes.status, 200);
  assert.ok(postRes.body.includes('"enabled":true'));
  assert.deepStrictEqual(h.notifications, [true]);

  const postObjReq = makeReq("/test-stream", "POST");
  const postObjRes = makeRes();
  h.instances[0].handler(postObjReq, postObjRes);
  postObjReq.emit("data", '{"enabled":"false","box":"mic","linesLimit":6,"maxChars":280}');
  postObjReq.emit("end");
  assert.strictEqual(postObjRes.status, 200);
  assert.ok(postObjRes.body.includes('"enabled":false'));
  assert.strictEqual(h.toggleCalls[h.toggleCalls.length - 1].enabled, false);
  assert.strictEqual(h.toggleCalls[h.toggleCalls.length - 1].box, "mic");
  assert.strictEqual(h.toggleCalls[h.toggleCalls.length - 1].linesLimit, 6);
  assert.strictEqual(h.toggleCalls[h.toggleCalls.length - 1].maxChars, 280);
  const postObjNotify = h.notifications[h.notifications.length - 1];
  assert.strictEqual(typeof postObjNotify, "object");
  assert.strictEqual(postObjNotify.enabled, false);
  assert.strictEqual(postObjNotify.box, "mic");
  assert.strictEqual(postObjNotify.linesLimit, 6);
  assert.strictEqual(postObjNotify.maxChars, 280);

  const badReq = makeReq("/test-stream", "POST");
  const badRes = makeRes();
  h.instances[0].handler(badReq, badRes);
  badReq.emit("data", "{bad");
  badReq.emit("end");
  assert.strictEqual(badRes.status, 400);

  const methodReq = makeReq("/test-stream", "PUT");
  const methodRes = makeRes();
  h.instances[0].handler(methodReq, methodRes);
  assert.strictEqual(methodRes.status, 405);

  const settingsReq = makeReq("/overlay-settings");
  const settingsRes = makeRes();
  h.instances[0].handler(settingsReq, settingsRes);
  assert.strictEqual(settingsRes.status, 200);
  assert.ok(settingsRes.body.includes("Overlay Settings"));

  const notFoundReq = makeReq("/nope");
  const notFoundRes = makeRes();
  h.instances[0].handler(notFoundReq, notFoundRes);
  assert.strictEqual(notFoundRes.status, 404);
}

function testRetryAndStop() {
  const h = buildRuntime();
  h.runtime.start();
  for (let i = 0; i < 21; i += 1) {
    const current = h.instances[h.instances.length - 1];
    current.listeners.error({ code: "EADDRINUSE" });
    assert.strictEqual(h.timers[h.timers.length - 1][1], 200);
    const [fn] = h.timers.shift();
    fn();
  }
  assert.strictEqual(h.runtime.getPort(), 8791);

  const resA = { endCalled: 0, end() { this.endCalled += 1; } };
  const resB = { endCalled: 0, end() { this.endCalled += 1; } };
  h.overlayClients.set(resA, "default");
  h.overlayClients.set(resB, "desktop");
  h.runtime.stop();
  assert.strictEqual(resA.endCalled, 1);
  assert.strictEqual(resB.endCalled, 1);
  assert.strictEqual(h.overlayClients.size, 0);
}

testRoutesAndSseLifecycle();
testRetryAndStop();
console.log("overlay_server_runtime.test.js: ok");
