(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.whatGuiTranscriptRecord = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  // Retained transcript history, independent of the short live caption window.
  //
  // One record per recognized segment, keyed by session/client/segment identity.
  // Segment and word times are absolute seconds into the client's recording
  // (<session_id>/<client_id>.wav on the service), so a record identifies its audio by
  // (sessionId, clientId) rather than a file path that only the service host can use.
  //
  // `original` is recognition output and is never modified. Corrections append to
  // `revisions`; corrected character offsets are not new word timestamps, so seeking
  // inside an edited passage must fall back to the segment bounds.

  function finiteOrNull(value) {
    const n = Number(value);
    return value !== null && value !== undefined && Number.isFinite(n) ? n : null;
  }

  function normalizeWords(words) {
    if (!Array.isArray(words)) return [];
    return words.map((w) => ({
      text: String((w && w.word) || ""),
      start: finiteOrNull(w && w.abs_start),
      end: finiteOrNull(w && w.abs_end),
    }));
  }

  function audioStatus(event, start, end) {
    if (event.recorded === false) return { available: false, reason: "not_recorded" };
    if (event.recorded !== true) return { available: false, reason: "recording_status_unknown" };
    if (start === null || end === null) return { available: false, reason: "no_timing" };
    return { available: true, reason: null };
  }

  // Older events may lack a segments array; treat the chunk as a single segment whose
  // bounds are the chunk bounds and which has no word timing.
  function segmentsOf(event) {
    if (Array.isArray(event.segments) && event.segments.length) return event.segments;
    const text = String(event.text || "");
    if (!text.trim()) return [];
    return [{
      id: event.chunk_index === undefined || event.chunk_index === null ? "" : `chunk-${event.chunk_index}`,
      abs_start: event.chunk_start,
      abs_end: event.chunk_end,
      text,
      words: [],
    }];
  }

  function createTranscriptStore({ now = () => Date.now() } = {}) {
    const byKey = new Map();
    let ordered = [];
    let unidentified = 0;

    function ingest(event, source) {
      if (!event || event.type !== "segment") return [];
      const sessionId = String(event.session_id || "");
      const clientId = String(event.client_id || "");
      const added = [];
      for (const seg of segmentsOf(event)) {
        const text = String((seg && seg.text) || "");
        if (!text.trim()) continue;
        const segmentId = String(seg.id || "");
        // Segment ids are unique within a client's append-only log; a repeat is a
        // re-delivery of the same recognition, not new speech. Without an id there is
        // nothing to deduplicate on, so keep it under a local key instead of dropping it.
        const key = segmentId
          ? `${sessionId}/${clientId}/${segmentId}`
          : `${sessionId}/${clientId}/unidentified-${++unidentified}`;
        if (byKey.has(key)) continue;
        const start = finiteOrNull(seg.abs_start);
        const end = finiteOrNull(seg.abs_end);
        const words = normalizeWords(seg.words);
        const record = {
          key,
          sessionId,
          clientId,
          segmentId,
          source: source || String(event.input_source_id || ""),
          inputSourceId: String(event.input_source_id || ""),
          recordingEpoch: String(event.recording_epoch || ""),
          start,
          end,
          original: Object.freeze({
            text,
            words: Object.freeze(words.map((w) => Object.freeze(w))),
          }),
          wordTiming: words.length > 0 && words.every((w) => w.start !== null && w.end !== null),
          audio: Object.freeze({ ...audioStatus(event, start, end), sessionId, clientId }),
          recognition: Object.freeze({
            engine: String(event.asr_engine || ""),
            model: String(event.asr_model || ""),
            language: String(event.language || ""),
            avgLogprob: finiteOrNull(seg.avg_logprob),
          }),
          revisions: [],
          receivedAt: now(),
        };
        byKey.set(key, record);
        ordered.push(record);
        added.push(record);
      }
      return added;
    }

    function currentText(record) {
      const last = record.revisions[record.revisions.length - 1];
      return last ? last.text : record.original.text;
    }

    // Where replay of `record` should start for a click on word `wordIndex`. Word
    // timing is used only for unedited text: after a correction, displayed character
    // positions no longer map to recognized words, so seeking uses the segment start.
    function seekTarget(record, wordIndex) {
      if (!record) return { ok: false, reason: "unknown_segment" };
      if (!record.audio.available) return { ok: false, reason: record.audio.reason };
      const base = { ok: true, sessionId: record.sessionId, clientId: record.clientId };
      const word = Number.isInteger(wordIndex) ? record.original.words[wordIndex] : null;
      if (record.revisions.length === 0 && word && word.start !== null) {
        return { ...base, start: word.start, precision: "word" };
      }
      return { ...base, start: record.start, precision: "segment" };
    }

    // Current text of the neighbouring segments in the same source lane.
    function contextFor(record) {
      const lane = ordered.filter((r) => r.source === record.source);
      const i = lane.indexOf(record);
      return {
        before: i > 0 ? currentText(lane[i - 1]).trim() : "",
        after: i >= 0 && i < lane.length - 1 ? currentText(lane[i + 1]).trim() : "",
      };
    }

    // A correction entry for replacing `record`'s current text with `correctedText`, or
    // null when nothing changes. Recognition output and its word timing are carried
    // unchanged; corrected text has no word timestamps of its own, so the audio interval
    // is the segment's. Missing audio or timing is stated rather than implied.
    function buildCorrection(record, correctedText, { now: at = new Date(), id } = {}) {
      const corrected = String(correctedText ?? "").trim();
      const previous = currentText(record).trim();
      if (corrected === previous) return null;
      const context = contextFor(record);
      const audio = record.audio.available
        ? { available: true, reason: null, recording: `${record.clientId}.wav`, start: record.start, end: record.end }
        : { available: false, reason: record.audio.reason, recording: null, start: null, end: null };
      const countWords = (text) => (text.trim() ? text.trim().split(/\s+/).length : 0);
      return {
        schema: "what.correction.v1",
        correction_id: id || `c${at.getTime().toString(36)}${Math.random().toString(36).slice(2, 8)}`,
        created_at: at.toISOString(),
        ts: at.getTime(),
        source: "user",
        session_id: record.sessionId,
        client_id: record.clientId,
        input_source_id: record.inputSourceId,
        capture_source: record.source,
        recording_epoch: record.recordingEpoch,
        segment_ids: [record.segmentId],
        revision: record.revisions.length + 1,
        edit_type: corrected ? "replace" : "delete",
        raw_text: record.original.text.trim(),
        previous_text: previous,
        corrected_text: corrected,
        word_count: { original: countWords(record.original.text), corrected: countWords(corrected) },
        original_words: record.original.words.map((w) => ({ word: w.text, start: w.start, end: w.end })),
        word_timing: record.wordTiming ? "original_words_only" : "unavailable",
        segment_meta: [{
          id: record.segmentId,
          abs_start: record.start,
          abs_end: record.end,
          avg_logprob: record.recognition.avgLogprob,
        }],
        audio_start: audio.start,
        audio_end: audio.end,
        audio,
        context_before: context.before,
        context_after: context.after,
        recognition: {
          engine: record.recognition.engine,
          model: record.recognition.model,
          language: record.recognition.language,
          avg_logprob: record.recognition.avgLogprob,
        },
        // Familiar-source profiles are a v0.2 concept; capture channel is not a speaker.
        source_profile: null,
      };
    }

    // Record a saved correction as the segment's latest revision.
    function applyCorrection(record, correction) {
      record.revisions.push(Object.freeze({
        revision: correction.revision,
        text: correction.corrected_text,
        correctionId: correction.correction_id,
        at: correction.created_at,
      }));
    }

    function segments(source) {
      return source ? ordered.filter((r) => r.source === source) : ordered.slice();
    }

    function clear() {
      byKey.clear();
      ordered = [];
    }

    return {
      ingest,
      segments,
      currentText,
      seekTarget,
      contextFor,
      buildCorrection,
      applyCorrection,
      clear,
      get: (key) => byKey.get(key) || null,
      get size() { return ordered.length; },
    };
  }

  return { createTranscriptStore };
});
