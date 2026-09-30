(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.whatGuiTranscriptView = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  // One transcript panel over a transcript store (lib/transcript_record.js).
  //
  // - New segments are appended, never re-rendered, so a selection or scroll position
  //   in older text survives incoming speech.
  // - The panel follows live text only while scrolled to the bottom. Scrolling up stops
  //   following; returnToLive() (or scrolling back down) resumes it.
  // - A modifier-click (Cmd or Ctrl; on macOS Ctrl-click
  //   arrives as a context-menu event) asks to replay from that word. Ordinary clicks
  //   and drags remain plain text selection.
  // - Double-click edits a segment in place. Enter or leaving the field saves through
  //   onEditCommit (which persists the correction first), Esc cancels. The panel stops
  //   following while editing so incoming speech can't scroll the edit away.

  function wordsMatchText(record) {
    const joined = record.original.words.map((w) => w.text).join("").replace(/\s+/g, " ").trim();
    return joined === record.original.text.replace(/\s+/g, " ").trim();
  }

  // Word spans are only offered when every word has timing and the words reproduce the
  // displayed text; otherwise the segment is one span and seeks to its start.
  function wordLevel(record) {
    return record.revisions.length === 0 && record.wordTiming && wordsMatchText(record);
  }

  function isSeekClick(event) {
    return Boolean(event && (event.metaKey || event.ctrlKey));
  }

  function createTranscriptPanel({
    document, container, store, onSeekClick, onFollowChange, onEditCommit,
    placeholder = "—", bottomThresholdPx = 24,
  }) {
    let follow = true;
    let pendingNew = 0;
    let count = 0;
    let playingEl = null;
    let editing = null; // { key, el }
    const segmentEls = new Map();

    function notify() {
      if (onFollowChange) onFollowChange({ follow, pendingNew });
    }

    function scrollToBottom() {
      container.scrollTop = container.scrollHeight;
    }

    function atBottom() {
      return container.scrollHeight - container.scrollTop - container.clientHeight <= bottomThresholdPx;
    }

    function showPlaceholder() {
      container.textContent = placeholder;
      container.classList.add("empty");
    }

    function renderContent(seg, record) {
      seg.textContent = "";
      seg.classList.toggle("edited", record.revisions.length > 0);
      seg.title = record.revisions.length > 0 ? `Edited. Recognized: "${record.original.text.trim()}"` : "";
      if (wordLevel(record)) {
        record.original.words.forEach((word, index) => {
          const w = document.createElement("span");
          w.className = "w";
          w.dataset.wordIndex = String(index);
          w.textContent = index === 0 ? word.text.replace(/^\s+/, "") : word.text;
          seg.appendChild(w);
        });
      } else {
        seg.textContent = store.currentText(record).trim();
      }
    }

    function renderRecord(record) {
      const seg = document.createElement("span");
      seg.className = "seg";
      seg.dataset.segKey = record.key;
      if (!record.audio.available) seg.classList.add("no-audio");
      renderContent(seg, record);
      seg.addEventListener("keydown", (event) => {
        if (!editing || editing.el !== seg) return;
        if (event.key === "Enter") {
          // Segments are single passages; a line break would join words in the saved text.
          event.preventDefault();
          if (!event.shiftKey) finishEdit(true);
        } else if (event.key === "Escape") {
          event.preventDefault();
          if (event.stopPropagation) event.stopPropagation();
          finishEdit(false);
        }
      });
      seg.addEventListener("blur", () => { if (editing && editing.el === seg) finishEdit(true); });
      return seg;
    }

    function refresh(key) {
      const el = segmentEls.get(key);
      const record = store.get(key);
      if (el && record) renderContent(el, record);
    }

    function startEdit(key) {
      const el = segmentEls.get(key);
      const record = store.get(key);
      if (!el || !record || editing) return;
      editing = { key, el };
      if (follow) {
        follow = false;
        notify();
      }
      el.textContent = store.currentText(record).trim();
      el.classList.add("editing");
      el.contentEditable = "plaintext-only";
      if (typeof el.focus === "function") el.focus();
      const selection = typeof document.getSelection === "function" ? document.getSelection() : null;
      if (selection && typeof document.createRange === "function") {
        const range = document.createRange();
        range.selectNodeContents(el);
        selection.removeAllRanges();
        selection.addRange(range);
      }
    }

    function finishEdit(save) {
      if (!editing) return Promise.resolve();
      const { key, el } = editing;
      editing = null;
      const text = el.textContent;
      el.contentEditable = "false";
      el.classList.remove("editing");
      if (!save || !onEditCommit) {
        refresh(key);
        return Promise.resolve();
      }
      el.classList.add("saving");
      return Promise.resolve()
        .then(() => onEditCommit(key, text))
        .catch(() => {})
        .then(() => {
          el.classList.remove("saving");
          refresh(key);
        });
    }

    function append(records) {
      if (!records.length) return;
      if (count === 0) {
        container.textContent = "";
        container.classList.remove("empty");
      }
      for (const record of records) {
        if (count > 0) container.appendChild(document.createTextNode(" "));
        const el = renderRecord(record);
        segmentEls.set(record.key, el);
        container.appendChild(el);
        count += 1;
      }
      if (follow) {
        scrollToBottom();
      } else {
        pendingNew += records.length;
        notify();
      }
    }

    function clear() {
      editing = null;
      segmentEls.clear();
      playingEl = null;
      count = 0;
      showPlaceholder();
      follow = true;
      pendingNew = 0;
      notify();
    }

    function returnToLive() {
      follow = true;
      pendingNew = 0;
      scrollToBottom();
      notify();
    }

    function setPlaying(key) {
      if (playingEl) playingEl.classList.remove("playing");
      playingEl = key ? segmentEls.get(key) || null : null;
      if (playingEl) playingEl.classList.add("playing");
    }

    function seekTargetOf(target) {
      let wordIndex = null;
      for (let el = target; el && el !== container; el = el.parentNode) {
        if (!el.dataset) continue;
        if (wordIndex === null && el.dataset.wordIndex !== undefined) wordIndex = Number(el.dataset.wordIndex);
        if (el.dataset.segKey) return { key: el.dataset.segKey, wordIndex };
      }
      return null;
    }

    function handleSeek(event) {
      if (!isSeekClick(event)) return;
      const hit = seekTargetOf(event.target);
      if (!hit) return;
      event.preventDefault();
      if (onSeekClick) onSeekClick(hit);
    }

    container.addEventListener("click", handleSeek);
    container.addEventListener("dblclick", (event) => {
      if (isSeekClick(event)) return;
      const hit = seekTargetOf(event.target);
      if (!hit) return;
      event.preventDefault();
      startEdit(hit.key);
    });
    // macOS delivers a physical Ctrl-click as a context-menu event.
    container.addEventListener("contextmenu", (event) => { if (event.ctrlKey) handleSeek(event); });
    container.addEventListener("scroll", () => {
      const bottom = atBottom();
      if (bottom === follow) return;
      follow = bottom;
      if (follow) pendingNew = 0;
      notify();
    });

    showPlaceholder();

    return {
      append,
      clear,
      returnToLive,
      setPlaying,
      refresh,
      startEdit,
      finishEdit,
      get editingKey() { return editing ? editing.key : null; },
      get follow() { return follow; },
      get pendingNew() { return pendingNew; },
    };
  }

  return { createTranscriptPanel, isSeekClick, wordLevel };
});
