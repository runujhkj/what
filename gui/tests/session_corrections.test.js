"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { appendSessionCorrection } = require("../lib/session_corrections");

const logsDir = fs.mkdtempSync(path.join(os.tmpdir(), "what-corrections-"));
try {
  const base = { schema: "what.correction.v1", session_id: "2026-09-18_007_T103758", client_id: "mic-q92ywvka" };
  const first = appendSessionCorrection({ logsDir, correction: { ...base, correction_id: "c1", corrected_text: "a" } });
  const second = appendSessionCorrection({ logsDir, correction: { ...base, correction_id: "c2", corrected_text: "b" } });
  const file = path.join(logsDir, "2026-09-18_007_T103758", "corrections.jsonl");
  assert.deepEqual(first, { ok: true, path: file });
  assert.deepEqual(second, { ok: true, path: file });
  const rows = fs.readFileSync(file, "utf8").trim().split("\n").map((l) => JSON.parse(l));
  assert.deepEqual(rows.map((r) => r.correction_id), ["c1", "c2"]); // appended, never rewritten

  assert.deepEqual(appendSessionCorrection({ logsDir, correction: { ...base, schema: "other" } }),
    { ok: false, error: "invalid_correction" });
  assert.deepEqual(appendSessionCorrection({ logsDir, correction: { ...base, session_id: "../escape" } }),
    { ok: false, error: "invalid_id" });
  assert.deepEqual(appendSessionCorrection({ logsDir, correction: null }), { ok: false, error: "invalid_correction" });
  assert.equal(fs.existsSync(path.join(logsDir, "..", "escape")), false);
} finally {
  fs.rmSync(logsDir, { recursive: true, force: true });
}
console.log("session_corrections tests passed");
