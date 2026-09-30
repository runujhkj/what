const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const { createSwitchQueue, routePlayback, createDefaultInputTracker } = require('../lib/device_switching');
const { stopProcess } = require('../lib/client_process_stop');
(async () => {
  const changes = [];
  const track = createDefaultInputTracker((next, prev) => changes.push([prev, next]));
  for (const name of ['A', 'B', 'A', null, 'B']) track({ ok: true, input: name ? { name } : null });
  track({ ok: false }); track({ ok: true, input: { name: 'B' } });
  assert.deepEqual(changes, [['A','B'], ['B','A'], ['A',null], [null,'B']]);
  const outputs = [];
  const duplex = createDefaultInputTracker(() => {}, (next, prev) => outputs.push([prev, next]));
  for (const name of ['speakers', 'headset', 'speakers']) {
    duplex({ ok: true, input: { name: 'same microphone' }, output: { name } });
  }
  assert.deepEqual(outputs, [['speakers','headset'], ['headset','speakers']]);
  const queue = createSwitchQueue();
  let release;
  const calls = [];
  const first = queue.run(async current => {
    calls.push('stop');
    await new Promise(resolve => { release = resolve; });
    if (current()) calls.push('start A');
  });
  await Promise.resolve(); await Promise.resolve();
  const second = queue.run(() => calls.push('start B'));
  const third = queue.run(() => calls.push('start C'));
  release(); await Promise.all([first, second, third]);
  assert.deepEqual(calls, ['stop', 'start C']);
  await assert.rejects(queue.run(() => { throw Error('unplugged'); }));
  await queue.run(() => calls.push('recovered'));
  assert.equal(calls.at(-1), 'recovered');
  const pending = queue.run(() => calls.push('must not restart'));
  await queue.cancel(); await pending;
  assert.equal(calls.at(-1), 'recovered');
  const audio = { currentTime: 42, setSinkId: async id => { audio.sinkId = id; } };
  for (const id of ['headphones', 'speakers', 'default', 'headphones']) await routePlayback(audio, id);
  assert.equal(audio.sinkId, 'headphones'); assert.equal(audio.currentTime, 42);
  await assert.rejects(routePlayback({}, 'headphones'), /cannot select/);
  await routePlayback({}, 'default');
  const proc = () => Object.assign(new EventEmitter(), { exitCode: null, stdin: { end() {} } });
  const child = proc(); const signals = [];
  await stopProcess(child, { graceMs: 1, killMs: 20, signal(p, sig) {
    signals.push(sig); if (sig === 'SIGKILL') p.emit('exit');
  } });
  assert.deepEqual(signals, ['SIGTERM', 'SIGKILL']);
  assert.equal(child.listenerCount('exit'), 0);
  await assert.rejects(stopProcess(proc(), { graceMs: 1, killMs: 1, signal() {} }), /did not stop/);
  console.log('device_switching.test.js: ok');
})().catch(error => { console.error(error); process.exitCode = 1; });
