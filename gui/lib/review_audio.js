const path = require("path");
const { Transform } = require("stream");

// Review replay support for the main process.
//
// Recordings are read from the service's log directory on this machine
// (<logsDir>/<session_id>/<client_id>.wav), where segment and word times are WAV offsets.
// A remote service would need an audio endpoint instead; records identify audio by
// session/client precisely so that option stays open.

const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9_.-]*$/;

function isSafeId(value) {
  return typeof value === "string" && SAFE_ID.test(value) && !value.includes("..");
}

// Returns { ok, path, sampleRate, channels, durationSec } or { ok: false, reason }.
function resolveRecording({ logsDir, sessionId, clientId, fsImpl = require("fs") }) {
  if (!isSafeId(sessionId) || !isSafeId(clientId)) return { ok: false, reason: "invalid_id" };
  const file = path.join(logsDir, sessionId, `${clientId}.wav`);
  let header;
  let size;
  try {
    size = fsImpl.statSync(file).size;
    const fd = fsImpl.openSync(file, "r");
    try {
      header = Buffer.alloc(44);
      fsImpl.readSync(fd, header, 0, 44, 0);
    } finally {
      fsImpl.closeSync(fd);
    }
  } catch (_) {
    return { ok: false, reason: "recording_missing" };
  }
  if (size < 44 || header.toString("ascii", 0, 4) !== "RIFF" || header.toString("ascii", 8, 12) !== "WAVE") {
    return { ok: false, reason: "recording_unreadable" };
  }
  const channels = header.readUInt16LE(22);
  const sampleRate = header.readUInt32LE(24);
  const bitsPerSample = header.readUInt16LE(34);
  const bytesPerSecond = sampleRate * channels * (bitsPerSample / 8);
  if (!bytesPerSecond) return { ok: false, reason: "recording_unreadable" };
  // The service rewrites the header as it appends; the file size is the live length.
  return { ok: true, path: file, sampleRate, channels, durationSec: (size - 44) / bytesPerSecond };
}

// While review playback is active, desktop tap audio is replaced with silence of the
// same length before it reaches the desktop client. Capture keeps running (restarting
// ScreenCaptureKit can re-prompt for permission), the recording keeps its timeline, and
// the replayed audio is not transcribed again as fresh desktop speech. Activation
// expires on its own so a crashed renderer cannot leave desktop capture silenced.
function createReviewSuppressor({ now = () => Date.now() } = {}) {
  let activeUntil = 0;

  function isActive() {
    return now() < activeUntil;
  }

  function setActive(active, maxMs) {
    const limit = Math.max(0, Math.min(Number(maxMs) || 0, 6 * 60 * 60 * 1000));
    activeUntil = active && limit > 0 ? now() + limit : 0;
    return { active: isActive() };
  }

  function createTransform() {
    return new Transform({
      transform(chunk, _encoding, callback) {
        callback(null, isActive() ? Buffer.alloc(chunk.length) : chunk);
      },
    });
  }

  // Each tap connection gets its own transform; ending it never ends the client's stdin,
  // so the client survives tap reconnects.
  function pipeTapToClient(socket, stdin) {
    socket.pipe(createTransform()).pipe(stdin, { end: false });
  }

  return { isActive, setActive, createTransform, pipeTapToClient };
}

module.exports = { resolveRecording, createReviewSuppressor, isSafeId };
