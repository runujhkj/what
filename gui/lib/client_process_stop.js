// Wait for capture and its child process group to stop before opening another device.
function stopProcess(proc, { signal, graceMs = 2000, killMs = 2000 } = {}) {
  if (!proc || proc.exitCode !== null || proc.signalCode) return Promise.resolve();
  return new Promise((resolve, reject) => {
    let timer;
    const finish = () => { clearTimeout(timer); proc.removeListener('exit', finish); resolve(); };
    proc.once('exit', finish);
    timer = setTimeout(() => {
      timer = setTimeout(() => {
        proc.removeListener('exit', finish);
        reject(new Error('Audio capture did not stop; retry after the capture process exits.'));
      }, killMs);
      signal(proc, 'SIGKILL');
    }, graceMs);
    try { proc.stdin.end(); } catch (_) {}
    signal(proc, 'SIGTERM');
  });
}
module.exports = { stopProcess };
