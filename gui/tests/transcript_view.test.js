"use strict";
const assert = require("node:assert/strict");
const { createFakeDocument } = require("./fake_dom");
const { createTranscriptStore } = require("../lib/transcript_record");
const { createTranscriptPanel, wordLevel } = require("../lib/transcript_view");

function event(id, words, overrides = {}) {
  return {
    type: "segment", session_id: "sess", client_id: "mic-a", input_source_id: "mic",
    recording_epoch: "e000000000000", recorded: true,
    segments: [{
      id, abs_start: words[0][1], abs_end: words[words.length - 1][2],
      text: words.map((w) => w[0]).join(""),
      words: words.map(([word, abs_start, abs_end]) => ({ word, abs_start, abs_end })),
    }],
    ...overrides,
  };
}

function setup() {
  const document = createFakeDocument();
  const container = document.getElementById("micTranscriptOut");
  const store = createTranscriptStore();
  const seeks = [];
  const follows = [];
  const panel = createTranscriptPanel({
    document, container, store,
    onSeekClick: (hit) => seeks.push(hit),
    onFollowChange: (s) => follows.push(s),
  });
  const add = (e) => panel.append(store.ingest(e, "mic"));
  return { document, container, store, panel, seeks, follows, add };
}

// Empty panels show a placeholder; segments render as word spans, joined by spaces.
{
  const { container, add } = setup();
  assert.equal(container.textContent, "—");
  assert.equal(container.classList.contains("empty"), true);
  add(event("s1", [[" Hello", 1.0, 1.4], [" there.", 1.4, 1.9]]));
  add(event("s2", [[" Second", 3.0, 3.5]]));
  assert.equal(container.textContent, "Hello there. Second");
  assert.equal(container.classList.contains("empty"), false);
  const seg = container.children[0];
  assert.equal(seg.dataset.segKey, "sess/mic-a/s1");
  assert.deepEqual(seg.children.map((w) => w.dataset.wordIndex), ["0", "1"]);
}

// Modifier-click on a word reports segment and word; plain clicks keep text selection.
{
  const { container, seeks, add } = setup();
  add(event("s1", [[" Hello", 1.0, 1.4], [" there.", 1.4, 1.9]]));
  const word = container.children[0].children[1];
  // Events bubble to the container's listener with the word as target.
  const prevented = dispatchFrom(container, word, "click", { metaKey: true });
  assert.equal(prevented, true);
  dispatchFrom(container, word, "click", { ctrlKey: true });
  dispatchFrom(container, word, "contextmenu", { ctrlKey: true });
  dispatchFrom(container, word, "contextmenu", {});
  dispatchFrom(container, word, "click", {});
  assert.deepEqual(seeks, [
    { key: "sess/mic-a/s1", wordIndex: 1 },
    { key: "sess/mic-a/s1", wordIndex: 1 },
    { key: "sess/mic-a/s1", wordIndex: 1 },
  ]);
}

function dispatchFrom(listenerEl, target, type, props) {
  let prevented = false;
  const ev = { type, target, preventDefault: () => { prevented = true; }, ...props };
  for (const fn of listenerEl.listeners.get(type) || []) fn(ev);
  return prevented;
}

// Segments without usable word timing render as one span and seek at segment level.
{
  const { container, store, seeks, add } = setup();
  add(event("s1", [[" untimed", null, null]], {
    segments: [{ id: "s1", abs_start: 4, abs_end: 5, text: " untimed words", words: [{ word: " untimed" }] }],
  }));
  const seg = container.children[0];
  assert.equal(seg.children.length, 1); // a single text node, no word spans
  assert.equal(seg.textContent, "untimed words");
  dispatchFrom(container, seg, "click", { metaKey: true });
  assert.deepEqual(seeks, [{ key: "sess/mic-a/s1", wordIndex: null }]);
  assert.equal(wordLevel(store.segments()[0]), false);
}

// Missing audio is marked on the segment.
{
  const { container, add } = setup();
  add(event("s1", [[" Hi", 0, 1]], { recorded: false }));
  assert.equal(container.children[0].classList.contains("no-audio"), true);
}

// Following: new text scrolls to the bottom; scrolling up stops it and counts new
// segments; Return to live resumes.
{
  const { container, panel, follows, add } = setup();
  for (let i = 0; i < 10; i += 1) add(event(`s${i}`, [[` w${i}`, i, i + 0.5]]));
  assert.equal(container.scrollTop, container.scrollHeight);
  container.scrollTop = 0;
  container.dispatch("scroll");
  assert.equal(panel.follow, false);
  add(event("s10", [[" new", 10, 10.5]]));
  add(event("s11", [[" newer", 11, 11.5]]));
  assert.equal(container.scrollTop, 0); // reading position kept
  assert.deepEqual(follows.at(-1), { follow: false, pendingNew: 2 });
  panel.returnToLive();
  assert.equal(container.scrollTop, container.scrollHeight);
  assert.deepEqual(follows.at(-1), { follow: true, pendingNew: 0 });
  // Scrolling back to the bottom by hand also resumes following.
  container.scrollTop = 0;
  container.dispatch("scroll");
  container.scrollTop = container.scrollHeight - container.clientHeight;
  container.dispatch("scroll");
  assert.equal(panel.follow, true);
}

// The playing segment is highlighted; clear() resets content, follow and highlight.
{
  const { container, panel, add } = setup();
  add(event("s1", [[" a", 0, 1]]));
  add(event("s2", [[" b", 1, 2]]));
  panel.setPlaying("sess/mic-a/s2");
  assert.equal(container.children[2].classList.contains("playing"), true);
  panel.setPlaying("sess/mic-a/s1");
  assert.equal(container.children[2].classList.contains("playing"), false);
  assert.equal(container.children[0].classList.contains("playing"), true);
  panel.clear();
  assert.equal(container.textContent, "—");
  assert.equal(panel.follow, true);
}

// Double-click edits a segment in place; Enter saves via onEditCommit, which applies
// the revision; the segment then shows the corrected text as one span.
async function editing() {
  const document = createFakeDocument();
  const container = document.getElementById("micTranscriptOut");
  const store = createTranscriptStore();
  const commits = [];
  const follows = [];
  const panel = createTranscriptPanel({
    document, container, store,
    onFollowChange: (s) => follows.push(s),
    onEditCommit: async (key, text) => {
      commits.push([key, text]);
      const record = store.get(key);
      const correction = store.buildCorrection(record, text);
      if (correction) store.applyCorrection(record, correction);
    },
  });
  panel.append(store.ingest(event("s1", [[" Hello", 1.0, 1.4], [" there.", 1.4, 1.9]]), "mic"));
  panel.append(store.ingest(event("s2", [[" Next", 2.0, 2.4]]), "mic"));
  const seg = container.children[0];

  dispatchFrom(container, seg.children[1], "dblclick", {});
  assert.equal(panel.editingKey, "sess/mic-a/s1");
  assert.equal(seg.contentEditable, "plaintext-only");
  assert.equal(seg.textContent, "Hello there.");
  assert.equal(panel.follow, false); // incoming speech won't scroll the edit away
  assert.deepEqual(follows.at(-1), { follow: false, pendingNew: 0 });

  seg.textContent = "Hello, their.";
  const enter = { key: "Enter", preventDefault() { this.prevented = true; } };
  for (const fn of seg.listeners.get("keydown")) fn(enter);
  assert.equal(enter.prevented, true);
  await new Promise((r) => setImmediate(r));
  assert.deepEqual(commits, [["sess/mic-a/s1", "Hello, their."]]);
  assert.equal(panel.editingKey, null);
  assert.equal(seg.contentEditable, "false");
  assert.equal(seg.textContent, "Hello, their.");
  assert.equal(seg.classList.contains("edited"), true);
  assert.equal(seg.children.length, 1); // plain text now: seeks use the segment start
  assert.equal(seg.title, 'Edited. Recognized: "Hello there."');
  assert.equal(container.textContent, "Hello, their. Next");

  // Esc cancels without committing and restores the displayed text.
  const next = container.children[2];
  dispatchFrom(container, next, "dblclick", {});
  next.textContent = "discarded";
  const esc = { key: "Escape", preventDefault() {}, stopPropagation() { this.stopped = true; } };
  for (const fn of next.listeners.get("keydown")) fn(esc);
  assert.equal(esc.stopped, true); // Esc here must not also stop a replay
  assert.equal(commits.length, 1);
  assert.equal(next.textContent, "Next");
  assert.equal(next.children[0].dataset.wordIndex, "0"); // word spans restored

  // Shift+Enter neither saves nor inserts a line break; leaving the field saves.
  dispatchFrom(container, next, "dblclick", {});
  next.textContent = "Next one";
  const shiftEnter = { key: "Enter", shiftKey: true, preventDefault() { this.prevented = true; } };
  for (const fn of next.listeners.get("keydown")) fn(shiftEnter);
  assert.equal(shiftEnter.prevented, true);
  assert.equal(panel.editingKey, "sess/mic-a/s2");
  for (const fn of next.listeners.get("blur")) fn({});
  await new Promise((r) => setImmediate(r));
  assert.deepEqual(commits.at(-1), ["sess/mic-a/s2", "Next one"]);

  // A modifier double-click is a replay gesture, not an edit.
  dispatchFrom(container, seg, "dblclick", { metaKey: true });
  assert.equal(panel.editingKey, null);
}

editing().then(() => console.log("transcript_view tests passed"))
  .catch((err) => { console.error(err); process.exit(1); });
