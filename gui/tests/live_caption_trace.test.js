const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { registerOverlayIpcHandlers } = require("../lib/overlay_ipc_handlers");
const { normalizeOverlayPayload } = require("../lib/overlay_payload_contract");
const runtimeState = require("../lib/overlay_runtime_state");
const { createOverlayServerRuntime } = require("../lib/overlay_server_runtime");
const { createFakeDocument } = require("./fake_dom");

// Exercise the actual default renderer and generated browser script, using in-memory
// DOM/IPC/HTTP boundaries so this regression needs neither Electron nor open sockets.
const handlers = new Map();
const clients = new Map();
let payload = runtimeState.createInitialOverlayPayload();
let httpHandler;
const scoped = (box, value = payload) => runtimeState.overlayPayloadForBox(value, box);
registerOverlayIpcHandlers({
  ipcMain: { handle: (name, fn) => handlers.set(name, fn) },
  normalizeOverlayPayload, getOverlayPayload: () => payload,
  setOverlayPayload: (value) => { payload = value; }, overlayClients: clients,
  overlayPayloadForBox: scoped, encodeOverlay: JSON.stringify,
  getOverlayPort: () => 8790, getMainWindow: () => null,
  getOverlayTestStreamEnabled: () => false, setOverlayTestStreamEnabled() {},
});
const server = createOverlayServerRuntime({
  http: { createServer(fn) { httpHandler = fn; return { on() {}, listen() {}, close() {} }; } },
  normalizeOverlayBoxKey: runtimeState.normalizeOverlayBoxKey,
  encodeOverlay: JSON.stringify, overlayPayloadForBox: scoped, overlayClients: clients,
  getOverlayTestStreamEnabled: () => false, setOverlayTestStreamEnabled() {},
  notifyExternalTestStream() {}, overlayBasePort: 8790, setTimeoutFn() {}, logError() {},
});
server.start();
function browser(box) {
  let html = "";
  httpHandler({ url: `/overlay?box=${box}` }, { writeHead() {}, end: (body) => { html = body; } });
  const elements = { text: { textContent: "" }, header: { textContent: "" } };
  let eventSource;
  const context = vm.createContext({
    document: { getElementById: (id) => elements[id], documentElement: { style: { setProperty() {} } } },
    EventSource: function (url) { eventSource = this; this.url = url; },
  });
  vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1], context);
  httpHandler({ url: eventSource.url, on() {} }, {
    writeHead() {}, write: (line) => eventSource.onmessage({ data: line.slice(6).trim() }), end() {},
  });
  return elements;
}
const micBrowser = browser("mic");
const desktopBrowser = browser("desktop");
const combinedBrowser = browser("default");
const fakeDocument = createFakeDocument();
const elements = fakeDocument.byId;
const timers = new Map();
const delays = [];
let timerId = 0;
const context = vm.createContext({
  console, Promise, navigator: {},
  setTimeout: (fn, ms) => { delays.push(ms); timers.set(++timerId, fn); return timerId; },
  clearTimeout: (id) => timers.delete(id),
  document: fakeDocument,
});
context.window = context;
context.addEventListener = () => {};
context.whatControl = { setOverlayText: (value) => handlers.get("set-overlay-text")(null, value) };
for (const file of ["lib/live_caption_bridge.js", "lib/transcript_record.js", "lib/transcript_view.js", "lib/output_watch.js", "lib/device_switching.js", "renderer2.js"]) {
  vm.runInContext(fs.readFileSync(path.join(__dirname, "..", file), "utf8"), context);
}
const evaluate = (code) => vm.runInContext(code, context);
const fixture = process.env.WHAT_TRACE_RECOGNITION
  ? JSON.parse(fs.readFileSync(process.env.WHAT_TRACE_RECOGNITION, "utf8"))
  : { text: "A caption sample reaches the browser.", segments: [
    { id: "s1", text: "A caption sample reaches the browser.", words: [{ word: "A", start: 0.96, end: 1.1 }] },
  ] };
const event = { ...fixture, type: "segment" };
const wire = `EVENT:${JSON.stringify(event)}\n`;
evaluate('transition("STARTING")');
context.fragment = wire.slice(0, 13);
evaluate('ingestClientChunk(fragment, "mic")');
assert.equal(micBrowser.text.textContent, "");
context.fragment = wire.slice(13);
evaluate('ingestClientChunk(fragment, "mic")');
assert.equal(micBrowser.text.textContent, fixture.text.trim());
assert.equal(elements.get("micTranscriptOut").textContent, fixture.text.trim());
assert.equal(desktopBrowser.text.textContent, "");
assert.equal(payload.boxes.mic.segments[0].words.length, fixture.segments[0].words.length);
// The retained transcript keeps word metadata instead of reducing events to text.
assert.equal(evaluate('transcript.segments("mic").length'), fixture.segments.length);
assert.equal(evaluate('transcript.segments("mic")[0].original.words.length'), fixture.segments[0].words.length);
context.fragment = 'bad log\nEVENT:{broken}\nEVENT:{"type":"segment","text":"Desktop sample"}\n';
evaluate('transition("STARTED"); ingestClientChunk(fragment, "desktop")');
assert.equal(desktopBrowser.text.textContent, "Desktop sample");
assert.ok(combinedBrowser.text.textContent.includes(fixture.text.trim()));
assert.ok(combinedBrowser.text.textContent.includes("Desktop sample"));
// Normal empty heartbeats retain continuity; explicit lifecycle clears remove it.
handlers.get("set-overlay-text")(null, { text: "" });
assert.equal(desktopBrowser.text.textContent, "Desktop sample");
evaluate('transition("STOPPING")');
assert.equal(micBrowser.text.textContent, "");
assert.equal(desktopBrowser.text.textContent, "");
evaluate('transition("STARTING"); state.delay = 2');
context.fragment = wire;
evaluate('ingestClientChunk(fragment, "mic")');
assert.equal(micBrowser.text.textContent, "");
assert.equal(timers.size, 1);
assert.equal(delays.at(-1), 2000);
for (const [id, fn] of [...timers]) { timers.delete(id); fn(); }
assert.equal(micBrowser.text.textContent, fixture.text.trim());
evaluate('ingestClientChunk(fragment, "desktop"); transition("STOPPING")');
assert.equal(timers.size, 0);
assert.equal(desktopBrowser.text.textContent, "");
evaluate('ingestClientChunk(fragment, "mic")');
assert.equal(micBrowser.text.textContent, "");
evaluate('transition("STARTING"); state.delay = 0');
for (const text of ["One", "Two", "Three", "Four"]) {
  context.fragment = `EVENT:${JSON.stringify({ type: "segment", text })}\n`;
  evaluate('ingestClientChunk(fragment, "mic")');
}
assert.equal(micBrowser.text.textContent, "Two Three Four");
assert.equal(elements.get("micTranscriptOut").textContent, "One Two Three Four");
assert.equal(desktopBrowser.text.textContent, "");

// Review replay through the default renderer: modifier-click → recording lookup →
// desktop capture silenced → playback from the word → Stop restores everything.
const reviewCalls = [];
const audios = [];
context.whatControl.resolveRecording = async (sessionId, clientId) =>
  ({ ok: true, url: `file:///logs/${sessionId}/${clientId}.wav`, durationSec: 30 });
context.whatControl.setReviewPlayback = async (active, maxMs) => {
  reviewCalls.push([active, Math.round(maxMs)]);
  return { active };
};
context.Audio = class {
  constructor(url) {
    this.url = url; this.listeners = {}; this.currentTime = 0; this.paused = true;
    audios.push(this);
    setImmediate(() => this.fire("loadedmetadata"));
  }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  fire(type) { for (const fn of this.listeners[type] || []) fn(); }
  play() { this.paused = false; return Promise.resolve(); }
  pause() { this.paused = true; }
  load() { this.reset = true; }
  removeAttribute(name) { if (name === "src") this.url = null; }
};
const flush = async () => { for (let i = 0; i < 10; i += 1) await new Promise((r) => setImmediate(r)); };
const click = (el, target, props) => {
  for (const fn of el.listeners.get("click") || []) fn({ target, preventDefault() {}, ...props });
};

(async () => {
  evaluate('transition("STARTING")');
  const recorded = {
    type: "segment", session_id: "2026-09-18_007_T103758", client_id: "mic-q92ywvka",
    input_source_id: "mic", recording_epoch: "e000000000000", recorded: true, text: " Hello there.",
    segments: [{ id: "e000000000000-s000001", abs_start: 1.0, abs_end: 1.9, text: " Hello there.",
      words: [{ word: " Hello", abs_start: 1.0, abs_end: 1.4 }, { word: " there.", abs_start: 1.4, abs_end: 1.9 }] }],
  };
  context.fragment = `EVENT:${JSON.stringify(recorded)}\n`;
  evaluate('ingestClientChunk(fragment, "mic")');
  const micPanel = elements.get("micTranscriptOut");
  const seg = micPanel.children[0];
  const word = seg.children[1];
  assert.equal(micPanel.textContent, "Hello there.");

  click(micPanel, word, {}); // a plain click is text selection, not replay
  await flush();
  assert.equal(audios.length, 0);

  click(micPanel, word, { metaKey: true });
  await flush();
  assert.equal(audios.length, 1);
  assert.match(audios[0].url, /^file:\/\/\/logs\/2026-09-18_007_T103758\/mic-q92ywvka\.wav\?replay=\d+$/);
  assert.equal(audios[0].currentTime, 1.4);
  assert.equal(audios[0].paused, false);
  assert.deepEqual(reviewCalls, [[true, (30 - 1.4) * 1000 + 2000]]);
  assert.equal(elements.get("replayBar").hidden, false);
  assert.equal(elements.get("replayLabel").textContent, "▶ Replaying mic from 1.4s");
  assert.equal(seg.classList.contains("playing"), true);

  click(elements.get("replayStopBtn"), elements.get("replayStopBtn"), {});
  await flush();
  assert.equal(audios[0].paused, true);
  assert.deepEqual(reviewCalls.at(-1), [false, 0]);
  assert.equal(elements.get("replayBar").hidden, true);
  assert.equal(seg.classList.contains("playing"), false);

  // Unavailable audio is explained, not attempted.
  context.fragment = `EVENT:${JSON.stringify({ ...recorded, recorded: false,
    segments: [{ ...recorded.segments[0], id: "e000000000000-s000002" }] })}\n`;
  evaluate('ingestClientChunk(fragment, "mic")');
  click(micPanel, micPanel.children[2].children[0], { metaKey: true });
  await flush();
  assert.equal(audios.length, 1);
  assert.match(elements.get("statusLine").textContent, /can't replay: audio was not recorded/);

  // Corrections through the default renderer: double-click → edit → Enter saves the
  // correction first, then shows it; a failed save leaves the text unchanged.
  const saved = [];
  let saveResult = { ok: true, path: "/logs/x/corrections.jsonl" };
  context.whatControl.saveSessionCorrection = async (correction) => { saved.push(correction); return saveResult; };
  const dblclick = (el, target) => {
    for (const fn of el.listeners.get("dblclick") || []) fn({ target, preventDefault() {} });
  };
  const pressEnter = (el) => { for (const fn of el.listeners.get("keydown")) fn({ key: "Enter", preventDefault() {} }); };

  saveResult = { ok: false, error: "disk full" };
  dblclick(micPanel, word);
  seg.textContent = "Hello their.";
  pressEnter(seg);
  await flush();
  assert.equal(saved.length, 1);
  assert.equal(seg.textContent, "Hello there.");
  assert.match(elements.get("statusLine").textContent, /correction not saved: disk full/);

  saveResult = { ok: true, path: "/logs/x/corrections.jsonl" };
  dblclick(micPanel, seg.children[0]);
  seg.textContent = "Hello, their.";
  pressEnter(seg);
  await flush();
  const c = saved.at(-1);
  assert.deepEqual([c.session_id, c.client_id, c.capture_source, c.segment_ids[0]],
    ["2026-09-18_007_T103758", "mic-q92ywvka", "mic", "e000000000000-s000001"]);
  assert.deepEqual([c.raw_text, c.corrected_text, c.revision], ["Hello there.", "Hello, their.", 1]);
  assert.deepEqual([c.audio_start, c.audio_end, c.audio.recording], [1.0, 1.9, "mic-q92ywvka.wav"]);
  assert.equal(seg.textContent, "Hello, their.");
  assert.equal(seg.classList.contains("edited"), true);
  assert.match(elements.get("statusLine").textContent, /correction saved to mic transcript/);
  // Replay of an edited passage falls back to the segment start.
  click(micPanel, seg, { metaKey: true });
  await flush();
  assert.equal(audios.at(-1).currentTime, 1.0);
  assert.equal(elements.get("replayLabel").textContent, "▶ Replaying mic from 1.0s (segment start)");
  click(elements.get("replayStopBtn"), elements.get("replayStopBtn"), {});
  await flush();

  // A stalled media play promise must not block subsequent Ctrl-clicks or sinks.
  const normalPlay = context.Audio.prototype.play;
  context.Audio.prototype.play = function () { return new Promise(() => {}); };
  click(micPanel, seg, { ctrlKey: true });
  await flush();
  const stalled = audios.at(-1);
  const stalledUrl = stalled.url;
  context.Audio.prototype.play = normalPlay;
  click(micPanel, seg, { ctrlKey: true });
  await flush();
  const next = audios.at(-1);
  assert.notEqual(next, stalled);
  assert.notEqual(next.url, stalledUrl);
  assert.equal(stalled.reset, true);
  assert.equal(next.paused, false);
  assert.equal(elements.get("replayBar").hidden, false);
  next.fire("ended");
  await flush();
  assert.equal(elements.get("replayBar").hidden, true);
  click(micPanel, seg, { ctrlKey: true });
  await flush();
  assert.equal(audios.at(-1).paused, false);
  click(elements.get("replayStopBtn"), elements.get("replayStopBtn"), {});
  await flush();

  // File → Open Session: both panels are rebuilt from the saved events, corrections become
  // the displayed revisions, Start keeps them (and resumes the session), New Session clears.
  const contexts = [];
  context.whatControl.setSessionContext = async (id) => { contexts.push(id); return { ok: true }; };
  evaluate('transition("STOPPED")');
  const savedSeg = (client, source, id, start, text) => ({
    type: "segment", session_id: "2026-09-20_001_T090000", client_id: client, input_source_id: source,
    recorded: true, segments: [{ id, abs_start: start, abs_end: start + 1, text }],
  });
  context.sessionPayload = {
    sessionId: "2026-09-20_001_T090000",
    events: [
      { source: "mic", event: savedSeg("mic-a", "mic", "s1", 1, "Good morning.") },
      { source: "desktop", event: savedSeg("desktop-b", "desktop", "s1", 2, "Welcome back.") },
      { source: "mic", event: savedSeg("mic-a", "mic", "s2", 3, "Shall we start?") },
    ],
    corrections: [{
      schema: "what.correction.v1", session_id: "2026-09-20_001_T090000", client_id: "mic-a",
      segment_ids: ["s2"], revision: 1, corrected_text: "Shall we begin?", correction_id: "c1",
      created_at: "2026-09-20T09:00:10.000Z",
    }],
  };
  evaluate("loadSession(sessionPayload)");
  assert.equal(elements.get("micTranscriptOut").textContent, "Good morning. Shall we begin?");
  assert.equal(elements.get("desktopTranscriptOut").textContent, "Welcome back.");
  assert.match(elements.get("statusLine").textContent, /opened session 2026-09-20_001_T090000 \(3 segments, 1 edit\)/);
  assert.equal(evaluate("openedSessionId"), "2026-09-20_001_T090000");
  assert.equal(contexts.at(-1), "2026-09-20_001_T090000");
  evaluate('transition("STARTING", { keepTranscript: Boolean(openedSessionId) })');
  assert.equal(elements.get("micTranscriptOut").textContent, "Good morning. Shall we begin?");
  evaluate('transition("STOPPED"); newSession()');
  assert.equal(evaluate("transcript.size"), 0);
  assert.equal(evaluate("openedSessionId"), null);
  assert.equal(contexts.at(-1), null);

  server.stop();
  console.log("live_caption_trace.test.js: default renderer → IPC → SSE → browser text passed");
})().catch((err) => { console.error(err); process.exit(1); });
