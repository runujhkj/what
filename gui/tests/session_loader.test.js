const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { loadSessionDir, panelFor, eventWallStart } = require("../lib/session_loader");

const root = fs.mkdtempSync(path.join(os.tmpdir(), "what-session-"));
const dir = path.join(root, "2026-09-20_001_T090000");
fs.mkdirSync(dir);
const T0 = 1758358800;
const line = (o) => JSON.stringify(o) + "\n";
const ev = (client, source, start, id, text, extra = {}) => ({
  type: "segment", session_id: "recorded-elsewhere", client_id: client, input_source_id: source,
  chunk_start: start, chunk_end: start + 1, stream_started_at: T0,
  segments: [{ id, abs_start: start, abs_end: start + 1, text }], ...extra,
});

// Two mic files (a device switch) and a desktop file; one torn line from a crash.
fs.writeFileSync(path.join(dir, "mic-a.jsonl"), line(ev("mic-a", "mic", 1, "s1", "first")) + '{"type":"seg');
fs.writeFileSync(path.join(dir, "mic-b.jsonl"),
  line(ev("mic-b", "mic", 0, "s1", "after switch", { stream_started_at: T0 + 10 })));
fs.writeFileSync(path.join(dir, "desktop-c.jsonl"), line(ev("desktop-c", "desktop", 5, "s1", "desktop says")));
fs.writeFileSync(path.join(dir, "corrections.jsonl"),
  line({ schema: "what.correction.v1", session_id: "old", client_id: "mic-a", segment_ids: ["s1"], revision: 1 }) +
  line({ schema: "something-else" }));
fs.writeFileSync(path.join(dir, "process.log"), "not a segment log\n");

const loaded = loadSessionDir({ dir });
assert.equal(loaded.ok, true);
assert.equal(loaded.sessionId, "2026-09-20_001_T090000");
assert.deepEqual(loaded.events.map((e) => [e.source, e.event.segments[0].text]), [
  ["mic", "first"], ["desktop", "desktop says"], ["mic", "after switch"],
]);
// The folder is the session: ids are rewritten so replay finds <folder>/<client>.wav.
assert.ok(loaded.events.every((e) => e.event.session_id === "2026-09-20_001_T090000"));
assert.equal(loaded.corrections.length, 1);
assert.equal(loaded.corrections[0].session_id, "2026-09-20_001_T090000");

assert.equal(panelFor({ input_source_id: "desktop" }, "x"), "desktop");
assert.equal(panelFor({}, "desktop-123"), "desktop");
assert.equal(panelFor({ input_source_id: "mixed" }, "x"), "mic");
// Older logs: estimate from wall_time written just after the chunk ended.
assert.equal(eventWallStart({ wall_time: 110, chunk_start: 8, chunk_end: 10 }), 108);

assert.equal(loadSessionDir({ dir: path.join(root, "..bad") }).ok, false);
assert.equal(loadSessionDir({ dir: path.join(root, "missing") }).ok, false);
fs.rmSync(root, { recursive: true, force: true });
console.log("session_loader.test.js: ok");
