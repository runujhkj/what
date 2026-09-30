// Browser-measured append-only lines. Upstream retention is not display eviction:
// once a line is sealed, only viewport overflow (or explicit reflow/reset) retires it.
function createCaptionLayout(measure) {
  let previous = [];
  let lines = [];
  let nextLineId = 0;
  let widthBefore = -1;
  let streamId = null;
  let lastChunk = -1;
  const wordsOf = (text) => String(text || '').match(/\S+/gu) || [];
  function append(words, width) {
    for (const word of words) {
      const last = lines.at(-1);
      if (last && measure([...last.words, word].join(' ')) <= width + 0.25) last.words.push(word);
      else lines.push({ id: ++nextLineId, words: [word] });
    }
  }
  function update(text, { width, maxLines, reflow = false, stream = null }) {
    const capacity = Math.max(0, Math.floor(maxLines));
    const geometryChanged = reflow || width !== widthBefore;
    let reset = false;
    if (stream && typeof stream.id === 'string' && Array.isArray(stream.chunks)) {
      if (stream.id !== streamId) {
        streamId = stream.id;
        lastChunk = -1;
        lines = [];
        reset = true;
      }
      // Recompose retained display text only on an intentional geometry/font change.
      if (geometryChanged) {
        const words = lines.flatMap(line => line.words);
        lines = [];
        append(words, width);
      }
      for (const chunk of stream.chunks) {
        if (!Number.isSafeInteger(chunk.id) || chunk.id <= lastChunk) continue;
        append(wordsOf(chunk.text), width);
        lastChunk = chunk.id;
      }
      previous = wordsOf(text);
    } else {
      const words = wordsOf(text);
      let overlap = Math.min(previous.length, words.length);
      for (; overlap > 0; overlap--) {
        if (previous.slice(-overlap).every((word, i) => word === words[i])) break;
      }
      reset = streamId !== null || !words.length || (!overlap && words.length > 0);
      streamId = null;
      if (reset) lines = [];
      if (geometryChanged) {
        lines = [];
        append(words, width);
      } else append(words.slice(reset ? 0 : overlap), width);
      previous = words;
    }
    widthBefore = width;
    // Bound display history independently of the upstream three-event snapshot.
    const historyLimit = Math.max(32, capacity * 2);
    if (lines.length > historyLimit) lines = lines.slice(-historyLimit);
    const visible = capacity ? lines.slice(-capacity) : [];
    const rows = visible.map(line => ({ id: line.id, text: line.words.join(' ') }));
    return {
      rows, lines: rows.map(row => row.text),
      hiddenLines: Math.max(0, lines.length - capacity),
      reset: reset || geometryChanged,
    };
  }
  return { update };
}
module.exports = { createCaptionLayout };
