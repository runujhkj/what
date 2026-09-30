// Own both children together: a failed capture must never leave a waiting client.
async function startLinuxDesktopCapture({ spawn, python, bin, args, cwd, env,
  suppressor, log, device = "default", timeoutMs = 15000 }) {
  let capture;
  let client;
  let transform;
  let stopping = false;
  let diagnostic = "";
  const isWindows = process.platform === "win32";
  function stop() {
    if (stopping) return;
    stopping = true;
    if (transform) transform.destroy();
    for (const child of [capture, client]) {
      if (!child) continue;
      child.stdout?.unpipe();
      child.stdin?.destroy();
      if (isWindows && child.pid) {
        // SIGTERM does not cascade on Windows, so the capture wrapper's ffmpeg child would
        // survive. taskkill /T ends the whole tree.
        try { spawn("taskkill", ["/pid", String(child.pid), "/T", "/F"]).on("error", () => {}); } catch (_) {}
        continue;
      }
      child.kill("SIGTERM");
      const timer = setTimeout(() => {
        if (child.exitCode === null && !child.signalCode) child.kill("SIGKILL");
      }, 2000);
      timer.unref();
      child.once("exit", () => clearTimeout(timer));
    }
  }
  try {
    capture = spawn(python, ["-m", "what.desktop_capture", "--device", device],
      { cwd, env, stdio: ["ignore", "pipe", "pipe"] });
    // Wait for PCM, not merely a successful spawn: pactl/FFmpeg may fail afterward.
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("Desktop capture produced no audio; check the default output monitor")), timeoutMs);
      const fail = (error) => { clearTimeout(timer); reject(error); };
      capture.on("error", fail);
      capture.stderr.on("data", data => { diagnostic = (diagnostic + data).slice(-4000); log(String(data)); });
      capture.once("exit", code => fail(new Error(diagnostic.trim() || `Desktop capture exited (${code})`)));
      capture.stdout.once("readable", () => {
        if (!capture.stdout.readableLength) return;
        clearTimeout(timer);
        resolve();
      });
    });
    client = spawn(bin, args, { cwd, env, stdio: ["pipe", "pipe", "pipe"] });
    await new Promise((resolve, reject) => { client.once("spawn", resolve); client.once("error", reject); });
    client.stdin.on("error", error => { log(`desktop input: ${error.message}\n`); stop(); });
    for (const child of [capture, client]) {
      child.on("error", error => { log(`desktop process: ${error.message}\n`); stop(); });
      child.on("exit", (code, signal) => { log(`desktop process exited (${signal || code})\n`); stop(); });
    }
    if (capture.exitCode !== null || capture.signalCode) throw new Error(diagnostic || "Desktop capture stopped during startup");
    client.stdout.on("data", data => log(String(data)));
    client.stderr.on("data", data => log(String(data)));
    transform = suppressor.createTransform();
    capture.stdout.pipe(transform).pipe(client.stdin);
    return { client, stop };
  } catch (error) {
    stop();
    throw error;
  }
}
module.exports = { startLinuxDesktopCapture };
