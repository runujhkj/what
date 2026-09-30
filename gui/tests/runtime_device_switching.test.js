const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const { createFakeDocument } = require('./fake_dom');
(async () => {
  const document = createFakeDocument();
  const calls = []; let release;
  const context = vm.createContext({ document, navigator: {}, console, setTimeout, clearTimeout, Promise });
  context.window = context; context.addEventListener = () => {};
  context.whatControl = {
    clientStop: async () => { calls.push('stop mic'); if (release === undefined) await new Promise(r => { release = r; }); },
    clientStart: async opts => calls.push(opts.micDevice),
    desktopClientStop: async () => calls.push('stop desktop'),
    stop: async () => calls.push('stop service'),
    setOverlayText: async () => {},
  };
  for (const file of ['live_caption_bridge','transcript_record','transcript_view','output_watch','device_switching']) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../lib', file + '.js'), 'utf8'), context);
  }
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../renderer2.js'), 'utf8'), context);
  const run = code => vm.runInContext(code, context);
  run('transition("STARTING")');
  run('ingestClientChunk(\'EVENT:{"type":"segment","text":"Retained speech."}\\n\', "mic")');
  const retained = run('transcript.segments("mic").length');
  assert.ok(retained > 0);
  run('state.phase="running"; dom.micModeSelect.value="mic"; savedMicDevice="A"; switchLiveInput()');
  await new Promise(setImmediate);
  run('savedMicDevice="B"; switchLiveInput(); savedMicDevice="C"; switchLiveInput()');
  release(); await new Promise(setImmediate); await new Promise(setImmediate);
  assert.deepEqual(calls, ['stop mic', 'stop mic', 'C']);
  assert.equal(run('state.phase'), 'running');
  assert.equal(run('transcript.segments("mic").length'), retained);
  for (let i = 0; i < 10; i++) {
    run(`savedMicDevice="device-${i}"; switchLiveInput()`);
    await new Promise(setImmediate); await new Promise(setImmediate);
    assert.equal(calls.at(-1), `device-${i}`);
  }
  assert.equal(run('transcript.segments("mic").length'), retained);
  // Stop invalidates the switch before it can reopen input capture.
  release = undefined; calls.length = 0;
  run('savedMicDevice="D"; switchLiveInput()');
  await new Promise(setImmediate);
  const stopped = run('stopSession()');
  release(); await stopped;
  assert.ok(!calls.includes('D'));
  assert.equal(run('state.phase'), 'idle');
  // Late recording resolution cannot replace the newer replay; failed output routing
  // clears both playback and desktop suppression.
  context.timed = { type: 'segment', session_id: 'session', client_id: 'mic', recorded: true,
    segments: [{ id: 'timed', text: 'Replay sample', abs_start: 2, abs_end: 4 }] };
  run('transcript.ingest(timed, "mic")');
  const audios = [], suppression = [];
  context.Audio = class {
    constructor() {
      this.listeners = {}; audios.push(this);
      queueMicrotask(() => this.listeners.loadedmetadata?.());
    }
    addEventListener(name, listener) { this.listeners[name] = listener; }
    async setSinkId(id) { if (id === 'bad') throw Error('output disconnected'); this.sinkId = id; }
    async play() { this.playing = true; }
    pause() { this.playing = false; }
    removeAttribute() {}
    load() { this.reset = true; }
  };
  context.whatControl.setReviewPlayback = async active => suppression.push(active);
  let resolveOld;
  context.whatControl.resolveRecording = () => new Promise(r => { resolveOld = r; });
  const oldReplay = run('startReplay("mic", {key:"session/mic/timed"})');
  context.whatControl.resolveRecording = async () => ({ok:true, url:'recording', durationSec:10});
  await run('startReplay("mic", {key:"session/mic/timed"})');
  resolveOld({ok:true, url:'old', durationSec:10}); await oldReplay;
  assert.equal(audios.length, 1); assert.equal(audios[0].playing, true);
  assert.equal(audios[0].currentTime, 2);
  await assert.rejects(run('savedPlaybackDevice="bad"; startReplay("mic", {key:"session/mic/timed"})'), /disconnected/);
  assert.equal(audios[0].reset, true);
  assert.equal(run('replay'), null);
  assert.equal(suppression.at(-1), false);
  console.log('runtime_device_switching.test.js: ok');
})().catch(error => { console.error(error); process.exitCode = 1; });
