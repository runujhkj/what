const path = require("path");
const { isSafeId } = require("./review_audio");

// Corrections from the default GUI are appended next to the session's recordings and
// transcripts (<logsDir>/<session_id>/corrections.jsonl), so each entry sits beside the
// audio its interval refers to. The log directory is git-ignored: corrections contain
// personal speech and must not end up in the repository by default.
function appendSessionCorrection({ logsDir, correction, fsImpl = require("fs") }) {
  if (!correction || correction.schema !== "what.correction.v1") return { ok: false, error: "invalid_correction" };
  if (!isSafeId(correction.session_id) || !isSafeId(correction.client_id)) {
    return { ok: false, error: "invalid_id" };
  }
  const dir = path.join(logsDir, correction.session_id);
  const file = path.join(dir, "corrections.jsonl");
  try {
    fsImpl.mkdirSync(dir, { recursive: true });
    fsImpl.appendFileSync(file, JSON.stringify(correction) + "\n");
    return { ok: true, path: file };
  } catch (err) {
    return { ok: false, error: String(err && err.message ? err.message : err) };
  }
}

module.exports = { appendSessionCorrection };
