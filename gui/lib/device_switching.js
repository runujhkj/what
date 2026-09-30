(function(root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.whatDeviceSwitching = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function() {
  // Serialize mutations, skip queued stale choices, and keep the queue usable after failure.
  function createSwitchQueue() {
    let tail = Promise.resolve();
    let generation = 0;
    return {
      run(operation, { coalesce = true } = {}) {
        const id = ++generation;
        const current = () => id === generation;
        const result = tail.catch(() => {}).then(() => (!coalesce || current()) ? operation(current) : undefined);
        tail = result;
        return result;
      },
      async cancel() { ++generation; await tail.catch(() => {}); },
    };
  }
  async function routePlayback(audio, sinkId) {
    if (typeof audio.setSinkId !== 'function') {
      if (sinkId && sinkId !== 'default') throw new Error('This platform cannot select a playback output; use system sound settings.');
      return;
    }
    await audio.setSinkId(sinkId === 'default' ? '' : sinkId);
  }
  function createDefaultInputTracker(onChange, onOutputChange = () => {}) {
    let initialized = false, previous, previousOutput;
    return snapshot => {
      if (!snapshot?.ok) return;
      const name = snapshot.input?.name || null;
      if (initialized && name !== previous) onChange(name, previous);
      const output = snapshot.output?.name || null;
      if (initialized && output !== previousOutput) onOutputChange(output, previousOutput);
      previous = name;
      previousOutput = output;
      initialized = true;
    };
  }
  return { createSwitchQueue, routePlayback, createDefaultInputTracker };
});
