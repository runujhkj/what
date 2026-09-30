function normalizeClientOpts(opts) {
  return {
    host: opts?.host || "127.0.0.1",
    port: Number(opts?.port || 8765),
    inputMode: opts?.inputMode || "mic",
    stdinRaw: Boolean(opts?.stdinRaw),
    filePath: opts?.filePath || "",
    realtime: Boolean(opts?.realtime),
    micEnabled: opts?.micEnabled !== false,
    micBackend: opts?.micBackend || "",
    micDevice: opts?.micDevice || "",
    desktopEnabled: Boolean(opts?.desktopEnabled),
    desktopBackend: opts?.desktopBackend || "",
    desktopDevice: opts?.desktopDevice || "",
    eventPrefix: opts?.eventPrefix || ""
  };
}

function sameClientOpts(a, b) {
  if (!a || !b) return false;
  return JSON.stringify(a) === JSON.stringify(b);
}

function decideClientStart({ hasRunning, lastOpts, nextOpts, forceRestart }) {
  if (!hasRunning) return "start";
  if (forceRestart) return "restart";
  if (sameClientOpts(lastOpts || {}, nextOpts || {})) return "reuse";
  if (!forceRestart) return "skip";
  return "restart";
}

function _uniqueClientId(prefix) {
  return prefix + "-" + Math.random().toString(36).slice(2, 10);
}

function buildClientArgs(normalized) {
  const args = ["client", "--local", "--captions-on"];
  // Always pass an explicit --client-id so WHAT_CLIENT_ID in .env or environment
  // variables can't cause duplicate_client_id when two clients run simultaneously.
  args.push("--client-id", _uniqueClientId("mic"));
  if (normalized.inputMode) args.push("--input", normalized.inputMode);
  if (normalized.stdinRaw) args.push("--stdin-raw");
  if (normalized.filePath) args.push("--file", normalized.filePath);
  if (normalized.realtime) args.push("--realtime");
  if (normalized.micEnabled) args.push("--mic-enabled");
  else args.push("--no-mic");
  if (normalized.host) args.push("--host", normalized.host);
  if (normalized.port) args.push("--port", String(normalized.port));
  if (normalized.micBackend) args.push("--mic-backend", normalized.micBackend);
  if (normalized.micDevice) args.push("--mic-device", normalized.micDevice);
  if (normalized.desktopEnabled) args.push("--desktop-enabled");
  else args.push("--no-desktop");
  if (normalized.desktopBackend) args.push("--desktop-backend", normalized.desktopBackend);
  if (normalized.desktopDevice) args.push("--desktop-device", normalized.desktopDevice);
  if (normalized.eventPrefix) args.push("--event-prefix", normalized.eventPrefix);
  return args;
}

module.exports = {
  normalizeClientOpts,
  sameClientOpts,
  decideClientStart,
  buildClientArgs
};

