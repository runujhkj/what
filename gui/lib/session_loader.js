"use strict";

// Read a session folder (<logs>/<session_id>/) back into what the transcript workspace needs
// to show it again: the segment events of every client log, tagged with the panel ("mic" or
// "desktop") they belong in, and the saved corrections. Replay then finds each recording
// through the usual resolve-recording path, since the files stay in the logs folder.
//
// Written by the service: <client_id>.jsonl (+ .wav). Written by the GUI: corrections.jsonl.
// See what/session_files.py for the same rules on the Python side.

const path = require("path");
const { isSafeId } = require("./review_audio");

const CORRECTIONS_NAME = "corrections.jsonl";

function parseJsonl(text) {
  const out = [];
  for (const line of String(text || "").split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      const item = JSON.parse(trimmed);
      if (item && typeof item === "object") out.push(item);
    } catch (_) {
      // A line cut short by a crash; the rest of the log is still usable.
    }
  }
  return out;
}

// The panel a client's events belong in. Mic and audio-file input both report "mic".
function panelFor(event, clientId) {
  const source = String(event.input_source_id || String(clientId || "").split("-")[0] || "");
  return source === "desktop" ? "desktop" : "mic";
}

// Wall-clock start (epoch s) of the event's chunk, for ordering events from several client
// logs (e.g. two mic files after a device switch). Mirrors recording_anchor() in Python.
function eventWallStart(event) {
  const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);
  const chunkStart = num(event.chunk_start) || 0;
  const anchor = num(event.stream_started_at);
  if (anchor !== null) return anchor + chunkStart;
  const wall = num(event.wall_time);
  const chunkEnd = num(event.chunk_end);
  if (wall !== null && chunkEnd !== null) return wall - chunkEnd + chunkStart;
  return wall !== null ? wall : 0;
}

function loadSessionDir({ dir, fsImpl = require("fs") }) {
  const sessionId = path.basename(dir);
  if (!isSafeId(sessionId)) return { ok: false, error: `unexpected session folder name: ${sessionId}` };
  let names;
  try {
    names = fsImpl.readdirSync(dir);
  } catch (err) {
    return { ok: false, error: `cannot read ${dir}: ${err.message || err}` };
  }
  const events = [];
  let order = 0;
  for (const name of names.slice().sort()) {
    if (!name.endsWith(".jsonl") || name === CORRECTIONS_NAME || !isSafeId(name)) continue;
    const clientId = name.slice(0, -".jsonl".length);
    let text;
    try {
      text = fsImpl.readFileSync(path.join(dir, name), "utf-8");
    } catch (_) {
      continue;
    }
    for (const event of parseJsonl(text)) {
      if (event.type !== "segment") continue;
      // The folder is the session now (it may have been restored from another machine).
      const normalized = { ...event, session_id: sessionId, client_id: event.client_id || clientId };
      events.push({ source: panelFor(normalized, normalized.client_id), event: normalized,
        at: eventWallStart(normalized), order: order++ });
    }
  }
  events.sort((a, b) => (a.at - b.at) || (a.order - b.order));

  let corrections = [];
  try {
    corrections = parseJsonl(fsImpl.readFileSync(path.join(dir, CORRECTIONS_NAME), "utf-8"))
      .filter((c) => c.schema === "what.correction.v1")
      .map((c) => ({ ...c, session_id: sessionId }));
  } catch (_) {
    corrections = [];
  }
  return {
    ok: true,
    sessionId,
    sessionDir: dir,
    events: events.map(({ source, event }) => ({ source, event })),
    corrections,
  };
}

module.exports = { loadSessionDir, panelFor, eventWallStart, parseJsonl };
