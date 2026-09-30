"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { PassThrough } = require("node:stream");
const { resolveRecording, createReviewSuppressor, isSafeId } = require("../lib/review_audio");

function wavBytes(pcm, sampleRate = 16000, channels = 1) {
  const header = Buffer.alloc(44);
  header.write("RIFF", 0, "ascii");
  header.writeUInt32LE(36 + pcm.length, 4);
  header.write("WAVE", 8, "ascii");
  header.write("fmt ", 12, "ascii");
  header.writeUInt32LE(16, 16);
  header.writeUInt16LE(1, 20);
  header.writeUInt16LE(channels, 22);
  header.writeUInt32LE(sampleRate, 24);
  header.writeUInt32LE(sampleRate * channels * 2, 28);
  header.writeUInt16LE(channels * 2, 32);
  header.writeUInt16LE(16, 34);
  header.write("data", 36, "ascii");
  header.writeUInt32LE(pcm.length, 40);
  return Buffer.concat([header, pcm]);
}

// Recordings resolve by session/client under the service log directory.
{
  const logsDir = fs.mkdtempSync(path.join(os.tmpdir(), "what-review-"));
  try {
    fs.mkdirSync(path.join(logsDir, "2026-09-18_007_T103758"));
    fs.writeFileSync(path.join(logsDir, "2026-09-18_007_T103758", "mic-q92ywvka.wav"),
      wavBytes(Buffer.alloc(16000 * 2 * 3)));
    const ok = resolveRecording({ logsDir, sessionId: "2026-09-18_007_T103758", clientId: "mic-q92ywvka" });
    assert.equal(ok.ok, true);
    assert.equal(ok.sampleRate, 16000);
    assert.equal(ok.durationSec, 3);
    assert.equal(ok.path, path.join(logsDir, "2026-09-18_007_T103758", "mic-q92ywvka.wav"));

    assert.deepEqual(resolveRecording({ logsDir, sessionId: "2026-09-18_007_T103758", clientId: "desktop-x" }),
      { ok: false, reason: "recording_missing" });
    fs.writeFileSync(path.join(logsDir, "2026-09-18_007_T103758", "junk.wav"), Buffer.alloc(64));
    assert.deepEqual(resolveRecording({ logsDir, sessionId: "2026-09-18_007_T103758", clientId: "junk" }),
      { ok: false, reason: "recording_unreadable" });
  } finally {
    fs.rmSync(logsDir, { recursive: true, force: true });
  }
}

// Ids from events can't escape the log directory.
for (const bad of ["..", "../etc", "a/b", "", ".hidden", "a\\b", null]) {
  assert.equal(isSafeId(bad), false, String(bad));
  assert.equal(resolveRecording({ logsDir: "/tmp", sessionId: bad, clientId: "mic" }).reason, "invalid_id");
}
assert.equal(isSafeId("2026-09-18_007_T103758"), true);

// Suppression replaces tap audio with same-length silence, then expires on its own.
{
  let t = 0;
  const suppressor = createReviewSuppressor({ now: () => t });
  const socket = new PassThrough();
  const stdin = new PassThrough();
  const received = [];
  stdin.on("data", (chunk) => received.push(Buffer.from(chunk)));
  suppressor.pipeTapToClient(socket, stdin);

  const audio = Buffer.from([1, 2, 3, 4, 5, 6]);
  socket.write(audio);
  assert.deepEqual(suppressor.setActive(true, 1000), { active: true });
  socket.write(audio);
  t = 1000; // limit reached: a stuck renderer can't silence desktop capture forever
  socket.write(audio);
  suppressor.setActive(true, 5000);
  suppressor.setActive(false);
  socket.write(audio);

  setImmediate(() => {
    assert.deepEqual(received.map((b) => [...b]), [
      [1, 2, 3, 4, 5, 6],
      [0, 0, 0, 0, 0, 0],
      [1, 2, 3, 4, 5, 6],
      [1, 2, 3, 4, 5, 6],
    ]);
    // A tap socket closing must not end the client's stdin (reconnects reuse it).
    socket.end();
    setImmediate(() => {
      assert.equal(stdin.writableEnded, false);
      console.log("review_audio tests passed");
    });
  });
}
