const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const { PassThrough } = require("node:stream");
const { startLinuxDesktopCapture } = require("../lib/linux_desktop_capture");
const { createReviewSuppressor } = require("../lib/review_audio");
function child() {
  const p = new EventEmitter();
  Object.assign(p, { stdout: new PassThrough(), stderr: new PassThrough(), stdin: new PassThrough(), exitCode: null });
  p.kill = () => { p.exitCode = 0; p.emit("exit", 0); };
  return p;
}
async function run() {
  const children = [];
  const suppressor = createReviewSuppressor();
  suppressor.setActive(true, 10000);
  const runtime = await startLinuxDesktopCapture({
    spawn(bin, args) {
      const p = child(); children.push(p);
      if (children.length === 1) {
        assert.deepEqual(args.slice(0, 2), ["-m", "what.desktop_capture"]);
        setImmediate(() => p.stdout.write(Buffer.from([1, 2, 3, 4])));
      } else setImmediate(() => p.emit("spawn"));
      return p;
    }, python: "python", bin: "what", args: [], suppressor, log() {},
  });
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(runtime.client.stdin.read(), Buffer.alloc(4));
  suppressor.setActive(false);
  children[0].stdout.write(Buffer.from([5, 6]));
  assert.deepEqual(runtime.client.stdin.read(), Buffer.from([5, 6]));
  runtime.stop();
  assert(children.every(p => p.exitCode === 0));
  let failed;
  await assert.rejects(startLinuxDesktopCapture({
    spawn() { failed = child(); setImmediate(() => failed.emit("error", new Error("ENOENT"))); return failed; },
    args: [], suppressor, log() {},
  }), /ENOENT/);
  assert.equal(failed.exitCode, 0);
  const brokenClient = [];
  await assert.rejects(startLinuxDesktopCapture({
    spawn() {
      const p = child(); brokenClient.push(p);
      setImmediate(() => {
        if (brokenClient.length === 1) p.stdout.write(Buffer.from([1, 2]));
        else p.emit("error", new Error("client unavailable"));
      });
      return p;
    }, args: [], suppressor, log() {},
  }), /client unavailable/);
  assert(brokenClient.every(p => p.exitCode === 0));
  let stalled;
  await assert.rejects(startLinuxDesktopCapture({
    spawn() { stalled = child(); return stalled; },
    args: [], suppressor, log() {}, timeoutMs: 5,
  }), /produced no audio/);
  assert.equal(stalled.exitCode, 0);
  let rejected;
  await assert.rejects(startLinuxDesktopCapture({
    spawn() { rejected = child(); setImmediate(() => { rejected.stderr.write("No monitor source"); rejected.kill(); }); return rejected; },
    args: [], suppressor, log() {},
  }), /No monitor source/);
}
run().catch(error => { console.error(error); process.exitCode = 1; });
