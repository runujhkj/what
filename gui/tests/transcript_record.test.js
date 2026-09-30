"use strict";
const assert = require("node:assert/strict");
const { createTranscriptStore } = require("../lib/transcript_record");

// Shape taken from a real service event (logs/<session>/<client>.jsonl).
function segmentEvent(overrides = {}) {
  return {
    type: "segment",
    session_id: "2026-09-18_007_T103758",
    client_id: "mic-q92ywvka",
    input_source_id: "mic",
    recording_epoch: "e000000000000",
    recorded: true,
    chunk_index: 2,
    chunk_start: 20.0,
    chunk_end: 23.0,
    text: "(laughs) - 10,000 years.",
    segments: [
      {
        id: "e000000000000-s000003", abs_start: 20.5, abs_end: 21.16, text: "(laughs)",
        words: [{ word: " (laughs)", abs_start: 20.5, abs_end: 21.16 }],
      },
      {
        id: "e000000000000-s000004", abs_start: 21.16, abs_end: 22.88, text: " - 10,000 years.",
        words: [
          { word: " -", abs_start: 21.16, abs_end: 21.3 },
          { word: " 10,000", abs_start: 21.3, abs_end: 22.1 },
          { word: " years.", abs_start: 22.1, abs_end: 22.88 },
        ],
      },
    ],
    ...overrides,
  };
}

// One record per segment, with identity, absolute timing, words and available audio.
{
  const store = createTranscriptStore({ now: () => 1000 });
  const added = store.ingest(segmentEvent(), "mic");
  assert.equal(added.length, 2);
  const rec = store.get("2026-09-18_007_T103758/mic-q92ywvka/e000000000000-s000004");
  assert.ok(rec);
  assert.equal(rec.source, "mic");
  assert.equal(rec.recordingEpoch, "e000000000000");
  assert.equal(rec.start, 21.16);
  assert.equal(rec.end, 22.88);
  assert.deepEqual(rec.original.words.map((w) => w.text), [" -", " 10,000", " years."]);
  assert.equal(rec.original.words[1].start, 21.3);
  assert.equal(rec.wordTiming, true);
  assert.deepEqual(rec.audio, {
    available: true, reason: null,
    sessionId: "2026-09-18_007_T103758", clientId: "mic-q92ywvka",
  });
  assert.equal(rec.receivedAt, 1000);
  assert.equal(store.currentText(rec), " - 10,000 years.");
}

// Recognition output is immutable; the display text follows the latest revision.
{
  const store = createTranscriptStore();
  const [rec] = store.ingest(segmentEvent(), "mic");
  assert.throws(() => { rec.original.text = "edited"; }, TypeError);
  assert.throws(() => { rec.original.words[0].start = 0; }, TypeError);
  rec.revisions.push({ text: "(laughs)!" });
  assert.equal(store.currentText(rec), "(laughs)!");
  assert.equal(rec.original.text, "(laughs)");
}

// Re-delivered segments are not duplicated; history is not capped.
{
  const store = createTranscriptStore();
  store.ingest(segmentEvent(), "mic");
  assert.equal(store.ingest(segmentEvent(), "mic").length, 0);
  for (let i = 0; i < 100; i += 1) {
    store.ingest(segmentEvent({
      segments: [{ id: `e000000000000-s1${String(i).padStart(5, "0")}`, abs_start: 30 + i, abs_end: 31 + i, text: `line ${i}`, words: [] }],
    }), "mic");
  }
  assert.equal(store.size, 102);
  assert.equal(store.segments("mic").length, 102);
  assert.equal(store.segments("desktop").length, 0);
}

// The same segment id from another client or session is a different record.
{
  const store = createTranscriptStore();
  store.ingest(segmentEvent(), "mic");
  assert.equal(store.ingest(segmentEvent({ client_id: "desktop-abc" }), "desktop").length, 2);
  assert.equal(store.segments("desktop").length, 2);
}

// Unavailable audio is explicit rather than assumed.
{
  const store = createTranscriptStore();
  const [notRecorded] = store.ingest(segmentEvent({ recorded: false }), "mic");
  assert.deepEqual([notRecorded.audio.available, notRecorded.audio.reason], [false, "not_recorded"]);

  const legacy = segmentEvent();
  delete legacy.recorded;
  const [unknown] = createTranscriptStore().ingest(legacy, "mic");
  assert.deepEqual([unknown.audio.available, unknown.audio.reason], [false, "recording_status_unknown"]);

  const [untimed] = createTranscriptStore().ingest(segmentEvent({
    segments: [{ id: "s1", text: "no times", words: [{ word: " no" }] }],
  }), "mic");
  assert.deepEqual([untimed.audio.available, untimed.audio.reason], [false, "no_timing"]);
  assert.equal(untimed.wordTiming, false);
}

// Events without a segments array fall back to chunk bounds with no word timing.
{
  const store = createTranscriptStore();
  const [rec] = store.ingest(segmentEvent({ segments: undefined, text: "whole chunk" }), "desktop");
  assert.equal(rec.segmentId, "chunk-2");
  assert.deepEqual([rec.start, rec.end, rec.wordTiming], [20.0, 23.0, false]);
}

// Seeking: word time when unedited, segment start as fallback, explicit when unavailable.
{
  const store = createTranscriptStore();
  const [, rec] = store.ingest(segmentEvent(), "mic");
  assert.deepEqual(store.seekTarget(rec, 2), {
    ok: true, sessionId: "2026-09-18_007_T103758", clientId: "mic-q92ywvka", start: 22.1, precision: "word",
  });
  assert.equal(store.seekTarget(rec, null).precision, "segment");
  assert.equal(store.seekTarget(rec, null).start, 21.16);
  assert.equal(store.seekTarget(rec, 99).precision, "segment");
  rec.revisions.push({ text: "ten thousand years" });
  assert.deepEqual([store.seekTarget(rec, 2).start, store.seekTarget(rec, 2).precision], [21.16, "segment"]);

  const [untimedWords] = createTranscriptStore().ingest(segmentEvent({
    segments: [{ id: "s", abs_start: 5, abs_end: 6, text: "x", words: [{ word: " x" }] }],
  }), "mic");
  assert.deepEqual([store.seekTarget(untimedWords, 0).start, store.seekTarget(untimedWords, 0).precision], [5, "segment"]);

  const [notRecorded] = createTranscriptStore().ingest(segmentEvent({ recorded: false }), "mic");
  assert.deepEqual(store.seekTarget(notRecorded, 0), { ok: false, reason: "not_recorded" });
  assert.deepEqual(store.seekTarget(null, 0), { ok: false, reason: "unknown_segment" });
}

// Corrections: provenance, preserved recognition, explicit timing/audio, revision chain.
{
  const store = createTranscriptStore();
  const event = segmentEvent({ asr_engine: "whisperkit", asr_model: "base", language: "en" });
  event.segments[1].avg_logprob = -0.44;
  const [first, rec] = store.ingest(event, "mic");
  const at = new Date("2026-09-18T12:00:00Z");
  assert.equal(store.buildCorrection(rec, "  - 10,000 years.  "), null); // unchanged text
  const c = store.buildCorrection(rec, "ten thousand years", { now: at, id: "c1" });
  assert.equal(c.schema, "what.correction.v1");
  assert.deepEqual(
    [c.correction_id, c.created_at, c.ts, c.source, c.session_id, c.client_id, c.input_source_id, c.capture_source],
    ["c1", "2026-09-18T12:00:00.000Z", at.getTime(), "user", "2026-09-18_007_T103758", "mic-q92ywvka", "mic", "mic"],
  );
  assert.deepEqual(c.segment_ids, ["e000000000000-s000004"]);
  assert.equal(c.recording_epoch, "e000000000000");
  assert.deepEqual([c.raw_text, c.previous_text, c.corrected_text], ["- 10,000 years.", "- 10,000 years.", "ten thousand years"]);
  assert.deepEqual([c.revision, c.edit_type], [1, "replace"]);
  assert.deepEqual(c.word_count, { original: 3, corrected: 3 });
  assert.deepEqual(c.original_words[1], { word: " 10,000", start: 21.3, end: 22.1 });
  assert.equal(c.word_timing, "original_words_only");
  assert.deepEqual(c.audio, { available: true, reason: null, recording: "mic-q92ywvka.wav", start: 21.16, end: 22.88 });
  assert.deepEqual([c.audio_start, c.audio_end], [21.16, 22.88]);
  assert.deepEqual(c.segment_meta, [{ id: "e000000000000-s000004", abs_start: 21.16, abs_end: 22.88, avg_logprob: -0.44 }]);
  assert.deepEqual([c.context_before, c.context_after], ["(laughs)", ""]);
  assert.deepEqual(c.recognition, { engine: "whisperkit", model: "base", language: "en", avg_logprob: -0.44 });
  assert.equal(c.source_profile, null);

  store.applyCorrection(rec, c);
  assert.equal(store.currentText(rec), "ten thousand years");
  assert.equal(rec.original.text, " - 10,000 years."); // recognition untouched
  assert.equal(store.contextFor(first).after, "ten thousand years");

  // A second edit chains from the first and can change the word count.
  const c2 = store.buildCorrection(rec, "ten thousand years ago", { now: at });
  assert.deepEqual([c2.revision, c2.previous_text, c2.raw_text], [2, "ten thousand years", "- 10,000 years."]);
  assert.deepEqual(c2.word_count, { original: 3, corrected: 4 });
  assert.match(c2.correction_id, /^c/);
  store.applyCorrection(rec, c2);
  assert.equal(rec.revisions.length, 2);

  // Deleting a segment's text is a correction too.
  assert.equal(store.buildCorrection(first, "   ").edit_type, "delete");

  // Missing audio or timing is explicit, never an apparently usable pair.
  const [unrecorded] = createTranscriptStore().ingest(segmentEvent({ recorded: false }), "mic");
  const u = store.buildCorrection(unrecorded, "Laughing");
  assert.deepEqual(u.audio, { available: false, reason: "not_recorded", recording: null, start: null, end: null });
  assert.deepEqual([u.audio_start, u.audio_end], [null, null]);
  const [untimed] = createTranscriptStore().ingest(segmentEvent({
    segments: [{ id: "s", abs_start: 1, abs_end: 2, text: "x y", words: [{ word: " x" }, { word: " y" }] }],
  }), "mic");
  assert.equal(store.buildCorrection(untimed, "x z").word_timing, "unavailable");
}

// Events with no segment id or chunk index are kept, never merged as duplicates.
{
  const store = createTranscriptStore();
  for (const text of ["One", "Two"]) store.ingest({ type: "segment", text }, "mic");
  assert.deepEqual(store.segments("mic").map((r) => r.original.text), ["One", "Two"]);
  assert.equal(store.segments("mic")[0].segmentId, "");
}

// Empty text and non-segment events are ignored; clear() resets history.
{
  const store = createTranscriptStore();
  assert.equal(store.ingest({ type: "status" }, "mic").length, 0);
  assert.equal(store.ingest(segmentEvent({ segments: [{ id: "s", text: "  ", abs_start: 0, abs_end: 1 }] }), "mic").length, 0);
  store.ingest(segmentEvent(), "mic");
  store.clear();
  assert.equal(store.size, 0);
  assert.equal(store.get("2026-09-18_007_T103758/mic-q92ywvka/e000000000000-s000003"), null);
}

console.log("transcript_record tests passed");
