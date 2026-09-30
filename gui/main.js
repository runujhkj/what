// First: hide the console window of every helper process on Windows (see the module).
require("./lib/windows_hide").hideChildConsoles(require("child_process"));
// Console logging is best-effort. A packaged app started from the Start menu (or by a
// launcher that has exited) may have no usable stdout/stderr; a failed write (EPIPE)
// would otherwise surface as an "uncaught exception" dialog.
for (const stream of [process.stdout, process.stderr]) {
  if (stream && typeof stream.on === "function") stream.on("error", () => {});
}
const { stopProcess } = require("./lib/client_process_stop");
const { app, BrowserWindow, ipcMain, dialog, shell, screen } = require("electron");
// Keep settings, the GPU runtime and (packaged) logs under a stable "What" folder rather
// than one named after the npm package. Must run before anything reads userData.
{
  const appData = app.getPath("appData");
  const userData = require("path").join(appData, "What");
  const legacy = require("path").join(appData, "what-gui");
  const fsSync = require("fs");
  if (!fsSync.existsSync(userData) && fsSync.existsSync(legacy)) {
    try { fsSync.renameSync(legacy, userData); } catch (_) {}
  }
  app.setPath("userData", userData);
}
const APP_ICON = require("path").join(__dirname, "icons", "icon.png");
const { spawn, spawnSync } = require("child_process");
const fs = require("fs");
const http = require("http");
const net = require("net");
const path = require("path");
const { pathToFileURL } = require("url");
const reviewAudio = require("./lib/review_audio");
const sessionCorrections = require("./lib/session_corrections");
const audioDefaults = require("./lib/audio_defaults");
const desktopAudioProbe = require("./desktop_audio_probe");
const desktopAudioManager = require("./desktop_audio_manager");
const audioRoutingManager = require("./audio_routing_manager");
const overlayPayloadContract = require("./lib/overlay_payload_contract");
const overlayRuntimeState = require("./lib/overlay_runtime_state");
const windowStateStore = require("./lib/window_state_store");
const uiPrefsDiskStore = require("./lib/ui_prefs_disk_store");
const clientStartup = require("./lib/client_startup");
const desktopIpcHandlers = require("./lib/desktop_ipc_handlers");
const runtimePaths = require("./lib/runtime_paths");
const pythonRuntime = require("./lib/python_runtime");
const micDevices = require("./lib/mic_devices");
const fileIpcHandlers = require("./lib/file_ipc_handlers");
const correctionsIpcHandlers = require("./lib/corrections_ipc_handlers");
const overlayIpcHandlers = require("./lib/overlay_ipc_handlers");
const overlayServerRuntimeFactory = require("./lib/overlay_server_runtime");
const mainOverlayTestStreamRuntime = require("./lib/main_overlay_test_stream_runtime");
const mainTestStreamBridge = require("./lib/main_test_stream_bridge");
const mainOverlayIngestGate = require("./lib/main_overlay_ingest_gate");
const mainOverlayBroadcastRuntime = require("./lib/main_overlay_broadcast_runtime");

let mainWindow = null;
let desktopAudioStubWindow = null;
let clientProc = null;
// The Python controller (control API on :8780). In a source checkout `what gui` starts it;
// a packaged app launches Electron directly, so main.js must start it itself.
let controllerProc = null;
let tapSocket = null;
let tapSocketPath = null;
let lastClientOpts = null;
let tapLaunchedByUs = false; // true when we spawned the tap (not a pre-existing one)

// Silences desktop tap audio during transcript replay (see lib/review_audio.js).
const reviewSuppressor = reviewAudio.createReviewSuppressor();
// Where the local service writes <session>/<client_id>.wav: its jsonl_dir ("logs" by
// default) relative to the repository root it runs from. WHAT_LOG_DIR overrides.
// Resolve the Python tree and a writable logs dir for both a source checkout and a
// packaged AppImage (see lib/runtime_paths.js).
const WHAT_PATHS = runtimePaths.computePaths({
  isPackaged: app.isPackaged,
  resourcesPath: process.resourcesPath,
  userDataDir: app.getPath("userData"),
  guiDir: __dirname,
  env: process.env,
});
const SERVICE_LOGS_DIR = WHAT_PATHS.logsDir;

// Second client process for desktop tap audio, used when both mic and desktop are active.
let desktopClientProc = null;
let linuxDesktopCapture = null;
let desktopTapSocket = null;
let desktopTapSocketPath = null;
let desktopTapLaunchedByUs = false;
let overlayPayload = overlayRuntimeState.createInitialOverlayPayload();
const overlayClients = new Map();
const overlayBasePort = Number(process.env.WHAT_OVERLAY_PORT || 8790);
const windowStatePath = path.join(app.getPath("userData"), "window-state.json");
const desktopStubWindowStatePath = path.join(app.getPath("userData"), "desktop-audio-stub-window-state.json");
const uiPrefsPath = path.join(app.getPath("userData"), "ui-prefs.json");

function normalizeOverlayPayload(payload) {
  if (overlayPayloadContract && typeof overlayPayloadContract.normalizeOverlayPayload === "function") {
    return overlayPayloadContract.normalizeOverlayPayload(payload);
  }
  return payload && typeof payload === "object" ? payload : {};
}

function coerceTestStreamEnabled(value) {
  if (typeof value === "string") {
    const token = value.trim().toLowerCase();
    if (token === "false" || token === "0" || token === "off" || token === "no") return false;
    if (token === "true" || token === "1" || token === "on" || token === "yes") return true;
  }
  return Boolean(value);
}

function overlayPayloadForBox(boxKey) {
  return overlayRuntimeState.overlayPayloadForBox(overlayPayload, boxKey);
}

const broadcastOverlayPayload = mainOverlayBroadcastRuntime.createOverlayBroadcaster({
  getOverlayPayload: () => overlayPayload,
  overlayPayloadForBox: (boxKey, payload) => overlayRuntimeState.overlayPayloadForBox(payload, boxKey),
  overlayClients,
  encodeOverlay: _encodeOverlay,
  log: (line) => {
    // eslint-disable-next-line no-console
    console.log(line);
  },
});

const localTestStreamRuntime = mainOverlayTestStreamRuntime.createLocalTestStreamRuntime({
  normalizeOverlayPayload,
  intervalMs: 500,
  linesLimit: 3,
  maxChars: 280,
  usePixelFit: true,
  onPayload: (payload, state) => {
    overlayPayload = payload;
    const c = state && state.constraints ? state.constraints : { mic: {}, desktop: {} };
    function compactTrace(trace) {
      const t = trace && typeof trace === "object" ? trace : {};
      return (
        `pref=${t.preferFallbackGeometry ? "fb" : "in"} ` +
        `L=${String(t.linesLimit || "-")} C=${String(t.maxChars || "-")} S=${String(t.maxSegments || "-")} ` +
        `W=${String(t.widthPx || "-")} P=${String(t.paddingPx || "-")} F=${String(t.fontUi || "-")} M=${String(t.maxLineChars || "-")}`
      );
    }
    const micTrace = compactTrace(c.mic && c.mic.authorityTrace);
    const deskTrace = compactTrace(c.desktop && c.desktop.authorityTrace);
    const micLines = Array.isArray(state && state.laneLines && state.laneLines.mic)
      ? state.laneLines.mic.map((v) => String(v || "").replace(/\n/g, "\\n"))
      : [];
    const deskLines = Array.isArray(state && state.laneLines && state.laneLines.desktop)
      ? state.laneLines.desktop.map((v) => String(v || "").replace(/\n/g, "\\n"))
      : [];
    const micLineDump = micLines.join(" || ").slice(0, 240);
    const deskLineDump = deskLines.join(" || ").slice(0, 240);
    // eslint-disable-next-line no-console
    console.log(
      `what_gui: local-test-stream tick seq=${Number(payload && payload.seq) || -1} ` +
      `trace='${String((payload && payload.trace_id) || "")}' ` +
      `mic_l=${state.laneLines.mic.length} desk_l=${state.laneLines.desktop.length} ` +
      `mic_lines_limit=${Number(c.mic && c.mic.linesLimit) || 0} desk_lines_limit=${Number(c.desktop && c.desktop.linesLimit) || 0} ` +
      `mic_max_chars=${Number(c.mic && c.mic.maxChars) || 0} desk_max_chars=${Number(c.desktop && c.desktop.maxChars) || 0} ` +
      `mic_max_line_chars=${Number(c.mic && c.mic.maxLineChars) || 0} desk_max_line_chars=${Number(c.desktop && c.desktop.maxLineChars) || 0} ` +
      `mic_width_px=${Number(c.mic && c.mic.widthPx) || 0} desk_width_px=${Number(c.desktop && c.desktop.widthPx) || 0} ` +
      `mic_padding_px=${Number(c.mic && c.mic.paddingPx) || 0} desk_padding_px=${Number(c.desktop && c.desktop.paddingPx) || 0} ` +
      `mic_font_ui=${Number(c.mic && c.mic.fontUi) || 0} desk_font_ui=${Number(c.desktop && c.desktop.fontUi) || 0} ` +
      `mic_auth='{${micTrace}}' desk_auth='{${deskTrace}}' ` +
      `mic_lines='${micLineDump}' desk_lines='${deskLineDump}'`
    );
    broadcastOverlayPayload();
  },
  onStateChange: (enabled) => {
    // eslint-disable-next-line no-console
    console.log(`what_gui: local-test-stream set enabled=${enabled}`);
  },
});

const setOverlayTestStreamEnabled = mainTestStreamBridge.createSetOverlayTestStreamEnabled({
  setConstraints: (next) => {
    const out = localTestStreamRuntime.setConstraints(next);
    try {
      const m = out && out.mic ? out.mic : {};
      const d = out && out.desktop ? out.desktop : {};
      // eslint-disable-next-line no-console
      console.log(
        "what_gui: test-stream constraints applied " +
        `in_box='${String(next && next.box || "")}' ` +
        `in_lines=${Number(next && next.linesLimit)} in_chars=${Number(next && next.maxChars)} ` +
        `in_seg=${Number(next && next.maxSegments)} in_w=${Number(next && next.widthPx)} ` +
        `in_pad=${Number(next && next.paddingPx)} in_font=${Number(next && next.fontUi)} ` +
        `raw{w='${String(next && next._debug_box_raw_width || "")}',font='${String(next && next._debug_box_raw_font || "")}',` +
        `pad='${String(next && next._debug_box_raw_padding || "")}',seg='${String(next && next._debug_box_raw_max_segments || "")}',` +
        `chars='${String(next && next._debug_box_raw_max_chars || "")}'} ` +
        `mic{lines=${Number(m.linesLimit) || 0},chars=${Number(m.maxChars) || 0},seg=${Number(m.segmentLimit) || 0},` +
        `w=${Number(m.widthPx) || 0},pad=${Number(m.paddingPx) || 0},font=${Number(m.fontUi) || 0},max_line=${Number(m.maxLineChars) || 0}} ` +
        `desktop{lines=${Number(d.linesLimit) || 0},chars=${Number(d.maxChars) || 0},seg=${Number(d.segmentLimit) || 0},` +
        `w=${Number(d.widthPx) || 0},pad=${Number(d.paddingPx) || 0},font=${Number(d.fontUi) || 0},max_line=${Number(d.maxLineChars) || 0}}`
      );
    } catch (_err) {
      // ignore telemetry errors
    }
    return out;
  },
  setEnabled: (enabled, box) => localTestStreamRuntime.setEnabled(enabled, box),
  coerceEnabled: coerceTestStreamEnabled,
});

const ingestOverlayPayload = mainOverlayIngestGate.createOverlayIngestGate({
  shouldAcceptIncomingOverlayPayload: (input) => mainOverlayTestStreamRuntime.shouldAcceptIncomingOverlayPayload(input),
  isLocalTestStreamEnabled: () => localTestStreamRuntime.isEnabled(),
  setOverlayPayload: (next) => {
    overlayPayload = next;
  },
  log: (line) => {
    // eslint-disable-next-line no-console
    console.log(line);
  },
});

const overlayServerRuntime = overlayServerRuntimeFactory.createOverlayServerRuntime({
  http,
  normalizeOverlayBoxKey: overlayRuntimeState.normalizeOverlayBoxKey,
  encodeOverlay: _encodeOverlay,
  overlayPayloadForBox: (boxKey) => overlayPayloadForBox(boxKey),
  overlayClients,
  getOverlayTestStreamEnabled: () => localTestStreamRuntime.isEnabled(),
  setOverlayTestStreamEnabled,
  notifyExternalTestStream: (payload) => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      const state = localTestStreamRuntime.getState();
      const outbound = payload && typeof payload === "object"
        ? {
            ...payload,
            enabled: Boolean(state && state.enabled),
            constraints: state && state.constraints ? { ...state.constraints } : undefined,
          }
        : {
            enabled: Boolean(payload),
            constraints: state && state.constraints ? { ...state.constraints } : undefined,
          };
      mainWindow.webContents.send("external-test-stream", outbound);
    }
  },
  overlayBasePort,
  setTimeoutFn: setTimeout,
  logError: (...args) => console.error(...args)
});

function displayWorkAreas() {
  try { return screen.getAllDisplays().map((d) => d.workArea); } catch (_) { return []; }
}

function loadWindowState() {
  const saved = windowStateStore.loadWindowStateFromDisk(fs, windowStatePath, { width: 900, height: 700 });
  return windowStateStore.fitToDisplays(saved, displayWorkAreas());
}

function saveWindowState(win) {
  windowStateStore.saveWindowStateToDisk(fs, path, windowStatePath, win);
}

function loadDesktopStubWindowState() {
  const saved = windowStateStore.loadWindowStateFromDisk(fs, desktopStubWindowStatePath, { width: 520, height: 420 });
  return windowStateStore.fitToDisplays(saved, displayWorkAreas());
}

function saveDesktopStubWindowState(win) {
  windowStateStore.saveWindowStateToDisk(fs, path, desktopStubWindowStatePath, win);
}

function loadUiPrefsDisk() {
  return uiPrefsDiskStore.loadUiPrefsDisk(fs, uiPrefsPath);
}

function saveUiPrefsDisk(prefs) {
  return uiPrefsDiskStore.saveUiPrefsDisk(fs, path, uiPrefsPath, prefs);
}

function normalizeClientOpts(opts) {
  return clientStartup.normalizeClientOpts(opts);
}

function sameClientOpts(a, b) {
  return clientStartup.sameClientOpts(a, b);
}

function sendClientLog(line) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("client-log", line);
  }
}

function sendDesktopClientLog(line) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("desktop-client-log", line);
  }
}

function resolveWhatCli() {
  return runtimePaths.resolveWhatCli({ pythonRoot: WHAT_PATHS.pythonRoot, env: process.env });
}

// Returns the .app bundle path for 'open -n' launch (LaunchServices gives the app
// its own audit session, so TCC uses com.what.coreaudio-tap independent of Electron).
// Build once with: native/what-coreaudio-tap/build.sh
function resolveTapApp() {
  if (process.env.WHAT_TAP_APP) return process.env.WHAT_TAP_APP;
  // Packaged macOS app: the prebuilt tap ships in resources/bin (see scripts/package/build_macos.sh).
  if (app.isPackaged) return path.join(process.resourcesPath, "bin", "WhatCoreAudioTap.app");
  return path.join(__dirname, "..", "bin", "WhatCoreAudioTap.app");
}

// Fallback binary path used when the .app bundle doesn't exist.
function resolveTapBin() {
  if (process.env.WHAT_TAP_BIN) return process.env.WHAT_TAP_BIN;
  const localTap = path.join(__dirname, "..", "bin", "what-coreaudio-tap");
  if (fs.existsSync(localTap)) return localTap;
  return "what-coreaudio-tap";
}

// ---------------------------------------------------------------------------
// Tap first-run setup helpers
// ---------------------------------------------------------------------------

const AGENT_LABEL = "com.what.coreaudio-tap";
const AGENT_SOCKET_PATH = "/tmp/what-coreaudio-tap.sock";

// Every tap the app starts gets this, and exits when this process exits (see
// bin/what-coreaudio-tap.swift), so a crash or force quit cannot leave one running.
function tapOwnerArgs() {
  return ["--owner-pid", String(process.pid)];
}

// The agent plist lives in the app's data dir, NOT ~/Library/LaunchAgents: launchd only
// auto-loads that folder at login, so an agent loaded from here lasts for this login
// session at most and is never relaunched on its own.
function tapPlistPath() {
  return path.join(app.getPath("userData"), `${AGENT_LABEL}.plist`);
}

// Older versions wrote a RunAtLoad + KeepAlive agent into ~/Library/LaunchAgents and removed
// it only on a clean quit, so after a crash or force quit launchd kept a tap running
// indefinitely and restarted it at every login. Remove that agent. The opt-in agent that
// native/what-coreaudio-tap/build.sh installs (WHAT_INSTALL_LAUNCHAGENT=1, no KeepAlive) is
// the user's choice and is left alone.
function retireLegacyTapAgent() {
  if (process.platform !== "darwin") return;
  const legacy = path.join(app.getPath("home"), "Library", "LaunchAgents", `${AGENT_LABEL}.plist`);
  let text;
  try { text = fs.readFileSync(legacy, "utf8"); } catch (_) { return; }
  if (!text.includes("<key>KeepAlive</key>")) return;
  try { spawnSync("launchctl", ["unload", legacy], { stdio: "ignore" }); } catch (_) {}
  try { fs.unlinkSync(legacy); } catch (_) {}
  console.log(`[tap] removed leftover LaunchAgent ${legacy}`);
}

function unloadTapAgent() {
  try { spawnSync("launchctl", ["remove", AGENT_LABEL], { stdio: "ignore" }); } catch (_) {}
  try { fs.unlinkSync(tapPlistPath()); } catch (_) {}
}

function writeTapPlist(binaryPath) {
  const plistPath = tapPlistPath();
  fs.mkdirSync(path.dirname(plistPath), { recursive: true });
  fs.writeFileSync(plistPath, [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">',
    '<plist version="1.0">',
    '<dict>',
    '    <key>Label</key>',
    `    <string>${AGENT_LABEL}</string>`,
    '    <key>ProgramArguments</key>',
    '    <array>',
    `        <string>${binaryPath}</string>`,
    '        <string>--socket-path</string>',
    `        <string>${AGENT_SOCKET_PATH}</string>`,
    '        <string>--persistent</string>',
    ...tapOwnerArgs().map((a) => `        <string>${a}</string>`),
    '    </array>',
    '    <key>RunAtLoad</key>',
    '    <true/>',
    // Restart after a crash only: the tap exits 0 when the app exits.
    '    <key>KeepAlive</key>',
    '    <dict>',
    '        <key>SuccessfulExit</key>',
    '        <false/>',
    '    </dict>',
    '    <key>StandardErrorPath</key>',
    '    <string>/tmp/what-coreaudio-tap.log</string>',
    '</dict>',
    '</plist>',
  ].join("\n") + "\n", "utf8");
  return plistPath;
}

function isTapAgentLoaded() {
  if (process.platform !== "darwin") return false;
  const r = spawnSync("launchctl", ["list", AGENT_LABEL], { stdio: "pipe" });
  return r.status === 0;
}

function loadTapAgent(plistPath) {
  // Clear any lingering `disable` override for this label before loading. Without
  // this, a prior `launchctl disable` (e.g. used to kill a leaked login-time tap)
  // silently blocks the agent from starting even after we (re)write the plist.
  try {
    spawnSync("launchctl", ["enable", `gui/${process.getuid()}/${AGENT_LABEL}`], { stdio: "pipe" });
  } catch (_) {}
  spawnSync("launchctl", ["unload", plistPath], { stdio: "pipe" });
  const r = spawnSync("launchctl", ["load", plistPath], { stdio: "pipe" });
  if (r.status !== 0) {
    const msg = r.stderr ? r.stderr.toString().trim() : "unknown error";
    throw new Error(`launchctl load failed: ${msg}`);
  }
}

function buildTapBinary(onLog) {
  return new Promise((resolve, reject) => {
    const buildSh = path.join(__dirname, "..", "native", "what-coreaudio-tap", "build.sh");
    if (!fs.existsSync(buildSh)) {
      reject(new Error(`build.sh not found at ${buildSh}`));
      return;
    }
    const child = spawn("bash", [buildSh], {
      cwd: path.join(__dirname, ".."),
      stdio: ["ignore", "pipe", "pipe"],
    });
    child.stdout.on("data", d => onLog(d.toString()));
    child.stderr.on("data", d => onLog(d.toString()));
    child.on("close", code => {
      if (code === 0) resolve();
      else reject(new Error(`build.sh exited with code ${code}`));
    });
  });
}

function tapLogHasTccDenial() {
  try {
    const log = fs.readFileSync("/tmp/what-coreaudio-tap.log", "utf8");
    return log.includes("declined") || log.includes("not permitted") || log.includes("-3801");
  } catch {
    return false;
  }
}

async function ensureTapSetup(onLog) {
  if (process.platform !== "darwin") return { ok: true, skipped: true };
  const tapApp = resolveTapApp();
  const tapBin = path.join(tapApp, "Contents", "MacOS", "WhatCoreAudioTap");
  const plist = tapPlistPath();

  // A source checkout rebuilds a tap older than its Swift source (e.g. one built before
  // --owner-pid existed). The packaged app ships no source, so this never triggers there.
  const tapSrc = path.join(__dirname, "..", "bin", "what-coreaudio-tap.swift");
  let tapStale = false;
  try { tapStale = fs.statSync(tapSrc).mtimeMs > fs.statSync(tapBin).mtimeMs; } catch (_) {}

  if (!fs.existsSync(tapBin) || tapStale) {
    const swiftcCheck = spawnSync("which", ["swiftc"], { stdio: "pipe" });
    if (swiftcCheck.status !== 0) {
      onLog("[setup] swiftc not found — install Xcode Command Line Tools: xcode-select --install\n");
      if (!tapStale) return { ok: false, error: "no_swiftc" };
    } else {
      onLog(`[setup] ${tapStale ? "Tap source changed" : "First run"}: building WhatCoreAudioTap.app (~15s)...\n`);
      try {
        await buildTapBinary(onLog);
        onLog("[setup] Build complete.\n");
      } catch (err) {
        onLog(`[setup] Build failed: ${err.message}\n`);
        if (!tapStale) return { ok: false, error: "build_failed" };
        onLog("[setup] Using the existing (older) tap build.\n");
      }
    }
  }

  // The plist names this app's PID, so write it and (re)load the agent every time: an agent
  // left loaded from an earlier session belongs to a process that is gone.
  onLog("[setup] Loading com.what.coreaudio-tap LaunchAgent...\n");
  try {
    if (isTapAgentLoaded()) unloadTapAgent();
    writeTapPlist(tapBin);
    loadTapAgent(plist);
  } catch (err) {
    onLog(`[setup] Failed to load LaunchAgent: ${err.message}\n`);
    return { ok: false, error: "load_failed" };
  }

  try {
    const sock = await connectToTapSocket(AGENT_SOCKET_PATH, 5000);
    sock.destroy();
    return { ok: true };
  } catch {
    if (tapLogHasTccDenial()) {
      onLog("[setup] Screen Recording permission needed.\n");
      onLog("[setup] Open System Settings → Privacy & Security → Screen & System Audio Recording\n");
      onLog("[setup] and enable 'What System Audio', then retry.\n");
      return { ok: false, needsPermission: true };
    }
    onLog("[setup] Tap socket not yet reachable — may still be starting.\n");
    return { ok: false, error: "timeout" };
  }
}

// Connect to the tap's Unix socket, retrying until it appears.
function connectToTapSocket(socketPath, timeoutMs = 6000) {
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + timeoutMs;
    function attempt() {
      const s = net.createConnection(socketPath);
      s.once("connect", () => resolve(s));
      s.once("error", () => {
        if (Date.now() >= deadline) { reject(new Error(`tap socket not ready after ${timeoutMs}ms`)); return; }
        setTimeout(attempt, 150);
      });
    }
    attempt();
  });
}

// Re-attach the audio pipe after the tap socket closes (LaunchAgent restart, any blip).
// clientProc keeps running; only the socket side reconnects.
async function tryReconnectTapSocket() {
  // tapSocketPath goes null in stopClient — that is the cancellation signal.
  if (!tapSocketPath || !clientProc || clientProc.exitCode !== null) return;
  sendClientLog("[tap] socket closed — reconnecting...\n");
  // Small pause so launchd has time to restart the tap and recreate the socket.
  await new Promise(r => setTimeout(r, 1500));
  if (!tapSocketPath || !clientProc || clientProc.exitCode !== null) return;
  try {
    const newSock = await connectToTapSocket(tapSocketPath, 8000);
    if (!tapSocketPath || !clientProc || clientProc.exitCode !== null) { newSock.destroy(); return; }
    tapSocket = newSock;
    newSock.on("error", err => sendClientLog(`[tap] socket error: ${err.message}\n`));
    newSock.on("close", tryReconnectTapSocket);
    reviewSuppressor.pipeTapToClient(newSock, clientProc.stdin);
    sendClientLog("[tap] socket reconnected\n");
  } catch (err) {
    sendClientLog(`[tap] reconnect failed: ${err.message}\n`);
  }
}

async function startClient(opts) {
  const normalized = normalizeClientOpts(opts || {});
  const forceRestart = Boolean(opts?.forceRestart);
  const decision = clientStartup.decideClientStart({
    hasRunning: Boolean(clientProc && clientProc.exitCode === null && !clientProc.signalCode),
    lastOpts: lastClientOpts || {},
    nextOpts: normalized,
    forceRestart
  });
  if (decision === "reuse") {
    return { ok: true, running: true };
  }
  if (decision === "skip") {
    sendClientLog("client already running; ignoring duplicate start request\n");
    return { ok: true, running: true, skipped: true, reason: "already_running" };
  }
  if (decision === "restart") {
    await stopClient();
  }
  const bin = resolveWhatCli();
  const args = clientStartup.buildClientArgs(normalized);
  if (process.env.WHAT_PYTHON && !process.env.WHAT_CLI) args.unshift("-m", "what");
  sendClientLog(`starting: ${bin} ${args.join(" ")}\n`);
  const cwd = WHAT_PATHS.pythonRoot;

  if (process.platform === "darwin" && normalized.stdinRaw && normalized.inputMode === "stdin") {
    // Fixed socket path shared with the persistent LaunchAgent tap.
    tapSocketPath = "/tmp/what-coreaudio-tap.sock";

    const tapApp = resolveTapApp();
    const tapBinInApp = path.join(tapApp, "Contents", "MacOS", "WhatCoreAudioTap");

    // First: check if a persistent tap is already running (LaunchAgent or user-launched).
    // If it is, connect immediately — this path has indefinite TCC because the tap was
    // started independently of Electron (no shared audit session).
    let connectedToExisting = false;
    try {
      tapSocket = await connectToTapSocket(tapSocketPath, 1200);
      sendClientLog(`[tap] connected to existing tap instance\n`);
      connectedToExisting = true;
    } catch (_) {
      // Not running — fall through to launch
    }

    if (!connectedToExisting) {
      tapLaunchedByUs = true;
      if (fs.existsSync(tapBinInApp)) {
        // Launch via 'open -n'. LaunchServices starts the app in its own audit session,
        // but on macOS 26 TCC still attributes responsibility to Electron (the opener),
        // giving only the ~45-60s grace period. This is the fallback path.
        // For indefinite capture: load the LaunchAgent printed by build.sh.
        sendClientLog(`[tap] launching via open -n (fallback — install LaunchAgent for indefinite capture)\n`);
        const opener = spawn("open", ["-n", tapApp, "--args", "--socket-path", tapSocketPath, ...tapOwnerArgs()],
          { detached: true, stdio: "ignore" });
        opener.unref();
      } else {
        const tapBin = resolveTapBin();
        sendClientLog(`[tap] WhatCoreAudioTap.app not found; launching fallback: ${tapBin}\n`);
        sendClientLog(`[tap] run native/what-coreaudio-tap/build.sh for proper TCC isolation\n`);
        const tp = spawn(tapBin, ["--socket-path", tapSocketPath, ...tapOwnerArgs()],
          { detached: true, stdio: "ignore" });
        tp.unref();
      }

      try {
        tapSocket = await connectToTapSocket(tapSocketPath, 10000);
        sendClientLog(`[tap] socket connected\n`);
      } catch (err) {
        sendClientLog(`[tap] failed to connect: ${err.message}\n`);
        sendClientLog(`[tap] for indefinite capture: load the LaunchAgent (see build.sh output)\n`);
      }
    }

    if (tapSocket) {
      tapSocket.on("error", (err) => sendClientLog(`[tap] socket error: ${err.message}\n`));
      // tryReconnectTapSocket re-attaches the pipe after a tap restart without
      // sending EOF to clientProc.stdin (the { end: false } pipe below).
      tapSocket.on("close", tryReconnectTapSocket);
    }
  }

  // detached: true creates a new process group so we can kill the entire group
  // (controller + any surviving children) with process.kill(-pid, signal).
  // TOKENIZERS_PARALLELISM=false silences the huggingface_hub fork warning that
  // appears each time the controller spawns a child process.
  const clientEnv = { ...process.env, TOKENIZERS_PARALLELISM: "false" };
  delete clientEnv.WHAT_CLIENT_ID; // prevent duplicate_client_id when env sets a fixed ID
  clientProc = spawn(bin, args, {
    env: clientEnv,
    cwd,
    detached: true,
  });
  lastClientOpts = normalized;
  if (tapSocket) {
    // { end: false }: don't close clientProc.stdin when the tap socket closes.
    // Keeps what client alive across tap restarts so reconnect can resume audio.
    reviewSuppressor.pipeTapToClient(tapSocket, clientProc.stdin);
  }
  clientProc.stdout.on("data", (data) => sendClientLog(data.toString()));
  clientProc.stderr.on("data", (data) => sendClientLog(data.toString()));
  clientProc.on("error", (err) => sendClientLog(`client error: ${err.message}\n`));
  const startedProc = clientProc;
  clientProc.on("exit", (code, signal) => {
    sendClientLog(`client exited (${signal || code})\n`);
    if (clientProc === startedProc) lastClientOpts = null;
  });
  await new Promise((resolve, reject) => {
    const ready = () => { startedProc.removeListener("error", failed); resolve(); };
    const failed = (err) => { startedProc.removeListener("spawn", ready); reject(err); };
    startedProc.once("spawn", ready);
    startedProc.once("error", failed);
  });
  return { ok: true, running: true };
}

async function stopClient() {
  // Null tapSocketPath first — tryReconnectTapSocket polls this as its cancel signal.
  tapSocketPath = null;
  if (tapSocket) {
    tapSocket.unpipe();
    tapSocket.destroy();
    tapSocket = null;
  }
  // Do NOT pkill the tap: the app's LaunchAgent tap stays up until the app quits.
  // A non-persistent tap exits on its own when its last socket client disconnects.
  if (!clientProc || clientProc.exitCode !== null) {
    return { ok: true, running: false };
  }
  const stopping = clientProc;
  await stopProcess(stopping, { signal(proc, sig) {
    if (process.platform === "win32") {
      // taskkill includes ffmpeg descendants; POSIX process groups do not exist on Windows.
      spawn("taskkill", ["/pid", String(proc.pid), "/T", "/F"]).on("error", () => {
        try { proc.kill(sig); } catch (_) {}
      });
    } else {
      try { process.kill(-proc.pid, sig); } catch (_) { try { proc.kill(sig); } catch (_) {} }
    }
  } });
  if (clientProc === stopping) { clientProc = null; lastClientOpts = null; }
  return { ok: true, running: false };
}

function clientStatus() {
  return { running: Boolean(clientProc && clientProc.exitCode === null && !clientProc.signalCode) };
}

const createWindow = () => {
  const state = loadWindowState();
  const win = new BrowserWindow({
    icon: APP_ICON,
    width: state.width,
    height: state.height,
    x: state.x,
    y: state.y,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  mainWindow = win;
  win.on("resize", () => saveWindowState(win));
  win.on("move", () => saveWindowState(win));
  win.on("close", () => saveWindowState(win));
  win.loadFile(path.join(__dirname, "index2.html"));
  win.webContents.on("did-finish-load", () => {
    if (appStatus) win.webContents.send("app-status", appStatus);
    win.webContents.send("external-test-stream", localTestStreamRuntime.isEnabled());
  });
};

const createDesktopAudioStubWindow = () => {
  if (desktopAudioStubWindow && !desktopAudioStubWindow.isDestroyed()) {
    desktopAudioStubWindow.focus();
    return;
  }
  const state = loadDesktopStubWindowState();
  const win = new BrowserWindow({
    icon: APP_ICON,
    width: state.width,
    height: state.height,
    x: state.x,
    y: state.y,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false
    }
  });
  desktopAudioStubWindow = win;
  win.on("resize", () => saveDesktopStubWindowState(win));
  win.on("move", () => saveDesktopStubWindowState(win));
  win.on("close", () => saveDesktopStubWindowState(win));
  win.on("closed", () => {
    desktopAudioStubWindow = null;
  });
  win.loadFile(path.join(__dirname, "desktop_audio_stub.html"));
};

// In a packaged app the bundled Python tree is read-only, so ensure a per-user venv exists
// and point the app's spawns at it. A source checkout (not packaged) keeps using its own
// .venv untouched.
function ensurePackagedPythonRuntime() {
  if (!app.isPackaged) return;
  if (process.env.WHAT_PYTHON || process.env.WHAT_CLI) return;
  // Installers that bundle Python ship it with every dependency preinstalled.
  const bundled = runtimePaths.bundledPython({ resourcesPath: process.resourcesPath });
  if (bundled) {
    process.env.WHAT_PYTHON = bundled;
    return;
  }
  // Double-clicking an AppImage gives no terminal, so capture pip/venv output and surface
  // its tail in the error dialog rather than pointing at a console that isn't there.
  let captured = "";
  const run = (cmd, args, opts) => {
    const r = spawnSync(cmd, args, { encoding: "utf-8", ...opts });
    captured += (r.stdout || "") + (r.stderr || "");
    return r;
  };
  try {
    const py = pythonRuntime.ensureVenv({
      userDataDir: app.getPath("userData"),
      pythonRoot: WHAT_PATHS.pythonRoot,
      run,
      log: (line) => { process.stdout.write(line); captured += line; },
    });
    process.env.WHAT_PYTHON = py;
  } catch (err) {
    const tail = captured.split("\n").slice(-16).join("\n");
    dialog.showErrorBox(
      "What: Python setup failed",
      `${err.message}\n\nNeeds Python 3.12 and internet on first run.\n\n${tail}`
    );
  }
}

// Status shown in the window while the packaged app prepares itself (the renderer shows it
// in place of "controller not reachable"). null clears it.
let appStatus = null;
function setAppStatus(message) {
  appStatus = message;
  if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send("app-status", message);
}

// On an NVIDIA machine the first start downloads the CUDA runtime (~1.3 GB). Do it before
// the controller starts: inside a service start it would outlast the GUI's readiness wait.
// Resolves when done or failed (the service then falls back to the CPU on its own).
function preparePackagedGpuRuntime() {
  if (!app.isPackaged || !process.env.WHAT_PYTHON) return Promise.resolve();
  return new Promise((resolve) => {
    let proc;
    try {
      proc = spawn(process.env.WHAT_PYTHON, ["-m", "what.cuda_runtime"],
        { cwd: WHAT_PATHS.pythonRoot, env: process.env, stdio: ["ignore", "pipe", "pipe"] });
    } catch (e) {
      resolve();
      return;
    }
    // Keep the output for diagnosis: a packaged app usually has no console to show it.
    const logPath = path.join(app.getPath("userData"), "gpu-runtime.log");
    const onLine = (data) => {
      const text = String(data);
      try { fs.appendFileSync(logPath, text); } catch (_) {}
      if (/installing cuBLAS/i.test(text)) {
        setAppStatus("First start: downloading the NVIDIA GPU runtime (about 1.3 GB). This happens once.");
      }
    };
    proc.stdout.on("data", onLine);
    proc.stderr.on("data", onLine);
    proc.on("error", () => resolve());
    proc.on("exit", () => { setAppStatus(null); resolve(); });
  });
}

// Start the Python controller the renderer talks to (control API on 127.0.0.1:8780). In a
// source checkout `what gui` starts it and Electron reuses it; a packaged app runs Electron
// directly, so without this the renderer reports "controller not reachable" and Start stays
// disabled. Dev is unaffected (guarded by app.isPackaged).
function startPackagedController() {
  if (!app.isPackaged) return;
  const python = runtimePaths.resolvePython({ pythonRoot: WHAT_PATHS.pythonRoot, env: process.env });
  const args = [
    "-m", "what", "control",
    "--host", "127.0.0.1", "--port", "8780",
    "--service-host", "127.0.0.1", "--service-port", "8765",
  ];
  try {
    const env = { ...process.env, TOKENIZERS_PARALLELISM: "false" };
    controllerProc = spawn(python, args, { cwd: WHAT_PATHS.pythonRoot, env, stdio: "inherit" });
    controllerProc.on("error", (e) => console.error("controller spawn error:", e.message));
    controllerProc.on("exit", (code) => {
      if (!_appShuttingDown) console.error(`controller exited early: code=${code}`);
      controllerProc = null;
    });
  } catch (e) {
    console.error("failed to start controller:", e.message);
  }
}

// A packaged app has no console, so a startup error would otherwise leave the app in the
// Dock with no window and no explanation. Record it and tell the user.
function reportStartupError(step, err) {
  const text = `${new Date().toISOString()} ${step}: ${(err && err.stack) || err}\n`;
  console.error(text);
  try { fs.appendFileSync(path.join(app.getPath("userData"), "startup-errors.log"), text); } catch (_) {}
  try { dialog.showErrorBox("What: startup error", `${step} failed:\n\n${(err && err.message) || err}`); } catch (_) {}
}

app.whenReady().then(() => {
  try {
    prepareRuntime();
  } catch (err) {
    reportStartupError("Preparing the runtime", err);
  }
  if (String(process.env.WHAT_GUI_MODE || "").trim() === "desktop-audio-stub") {
    createDesktopAudioStubWindow();
  } else {
    createWindow();
  }
  overlayServerRuntime.start();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      if (String(process.env.WHAT_GUI_MODE || "").trim() === "desktop-audio-stub") {
        createDesktopAudioStubWindow();
      } else {
        createWindow();
      }
    }
  });
}).catch((err) => reportStartupError("Starting the app", err));

function prepareRuntime() {
  retireLegacyTapAgent();
  // Packaged: the default cwd (bundled source) is read-only, so point the Python side's
  // recordings/transcripts at the writable logs dir. Inherited by every spawn below.
  if (app.isPackaged && !process.env.WHAT_JSONL_DIR) {
    try { fs.mkdirSync(WHAT_PATHS.logsDir, { recursive: true }); } catch (_) {}
    process.env.WHAT_JSONL_DIR = WHAT_PATHS.logsDir;
  }
  if (app.isPackaged) {
    // Bundled tools (ffmpeg) come first on PATH for every helper process.
    const bundledBin = path.join(process.resourcesPath, "bin");
    if (fs.existsSync(bundledBin)) process.env.PATH = `${bundledBin}${path.delimiter}${process.env.PATH || ""}`;
    // The macOS app ships the prebuilt WhisperKit worker next to ffmpeg.
    const bundledWorker = path.join(bundledBin, "what-whisperkit-worker");
    if (process.platform === "darwin" && !process.env.WHAT_WHISPERKIT_WORKER && fs.existsSync(bundledWorker)) {
      process.env.WHAT_WHISPERKIT_WORKER = bundledWorker;
    }
    // A writable home for the CUDA runtime wheels (the install folder may be read-only).
    if (!process.env.WHAT_CUDA_TARGET) process.env.WHAT_CUDA_TARGET = path.join(app.getPath("userData"), "cuda-runtime");
  }
  ensurePackagedPythonRuntime();
  preparePackagedGpuRuntime()
    .then(startPackagedController)
    .catch((err) => reportStartupError("Starting the controller", err));
}

// Ask the controller to cleanly stop its child processes (transcription client
// + Whisper service) before we SIGTERM the controller process itself.
// Without this, those children become orphans and keep consuming CPU after exit.
function _httpControllerStop(host, port) {
  return new Promise((resolve) => {
    const req = http.request(
      { host, port, path: "/control/stop", method: "POST",
        headers: { "Content-Type": "application/json" } },
      (res) => { res.resume(); resolve(); }
    );
    req.on("error", resolve);
    // stop_client + stop_service each wait up to 2s, so allow 6s total.
    req.setTimeout(6000, () => { req.destroy(); resolve(); });
    req.write("{}");
    req.end();
  });
}

// Wait for a child process to exit; SIGKILL it if it hasn't after timeoutMs.
function _waitForExit(proc, timeoutMs) {
  if (!proc || proc.exitCode !== null) return Promise.resolve();
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      try { proc.kill("SIGKILL"); } catch (_) {}
      resolve();
    }, timeoutMs);
    proc.once("exit", () => { clearTimeout(timer); resolve(); });
  });
}

let _appShuttingDown = false;

app.on("before-quit", (event) => {
  if (_appShuttingDown) return;
  _appShuttingDown = true;
  event.preventDefault();

  (async () => {
    // Stop local runtimes first (synchronous, fast).
    try { localTestStreamRuntime.stop(); } catch (_) {}
    try { overlayServerRuntime.stop(); } catch (_) {}

    // Tell the controller to stop its children (transcription client + Whisper
    // service) so they don't become orphaned processes after we kill the
    // controller.  Always send this — the guard was previously `clientProc &&
    // clientProc.exitCode === null`, which skipped the call for mic-only sessions
    // (where clientProc is null because the controller manages the what client
    // directly).  Skipping left the Whisper service alive on port 8765 after exit.
    // _httpControllerStop resolves on any network error, so this is always safe.
    const ctrlHost = "127.0.0.1";
    const ctrlPort = 8780;
    await _httpControllerStop(ctrlHost, ctrlPort);

    // If we started the controller (packaged app), terminate it so it and its Whisper
    // service don't outlive the GUI.
    if (controllerProc && controllerProc.exitCode === null) {
      try { controllerProc.kill("SIGTERM"); } catch (_) {}
    }

    // Let an in-flight desktop start settle before stopping its children.
    await desktopMutation;
    // Kill both client processes (mic and desktop tap) and wait for them to exit.
    stopDesktopClient();
    await _waitForExit(desktopClientProc, 3000);
    try { await stopClient(); } catch (err) { console.error("capture shutdown:", err.message); }
    await _waitForExit(clientProc, 3000);

    // Stop the tap now so the SCStream ends and the macOS "sharing" indicator clears
    // (each tap also exits on its own once this process is gone, via --owner-pid).
    // Remove our LaunchAgent rather than pkill: launchd would restart a killed tap.
    // For a directly-launched (non-LaunchAgent) tap, kill by full command path because
    // the process comm is truncated to 15 chars on macOS and won't match a 16-char -x pattern.
    if (isTapAgentLoaded()) {
      unloadTapAgent();
    } else if (tapLaunchedByUs || desktopTapLaunchedByUs) {
      try { spawnSync("pkill", ["-f", "WhatCoreAudioTap"], { stdio: "ignore" }); } catch (_) {}
    }
    tapLaunchedByUs = false;
    desktopTapLaunchedByUs = false;

    app.exit(0);
  })();
});

app.on("window-all-closed", () => {
  // Trigger before-quit (which does the real cleanup) then exit.
  app.quit();
});

// A terminal Ctrl+C or external `kill` bypasses Electron's normal window-close
// path entirely, so without these the before-quit cleanup above never runs. (A SIGKILL
// or crash still skips it; the taps' --owner-pid watch covers that case.)
process.on("SIGINT", () => app.quit());
process.on("SIGTERM", () => app.quit());

// ── Desktop client (second parallel process for simultaneous mic + desktop) ──

async function tryReconnectDesktopTapSocket() {
  if (!desktopTapSocketPath || !desktopClientProc || desktopClientProc.exitCode !== null) return;
  sendDesktopClientLog("[tap] socket closed — reconnecting...\n");
  await new Promise(r => setTimeout(r, 1500));
  if (!desktopTapSocketPath || !desktopClientProc || desktopClientProc.exitCode !== null) return;
  try {
    const newSock = await connectToTapSocket(desktopTapSocketPath, 8000);
    if (!desktopTapSocketPath || !desktopClientProc || desktopClientProc.exitCode !== null) {
      newSock.destroy(); return;
    }
    desktopTapSocket = newSock;
    newSock.on("error", err => sendDesktopClientLog(`[tap] socket error: ${err.message}\n`));
    newSock.on("close", tryReconnectDesktopTapSocket);
    reviewSuppressor.pipeTapToClient(newSock, desktopClientProc.stdin);
    sendDesktopClientLog("[tap] socket reconnected\n");
  } catch (err) {
    sendDesktopClientLog(`[tap] reconnect failed: ${err.message}\n`);
  }
}

function stopDesktopClient() {
  if (linuxDesktopCapture) {
    linuxDesktopCapture.stop();
    linuxDesktopCapture = null;
    return { ok: true, running: false };
  }
  desktopTapSocketPath = null;
  if (desktopTapSocket) {
    desktopTapSocket.unpipe();
    desktopTapSocket.destroy();
    desktopTapSocket = null;
  }
  if (!desktopClientProc || desktopClientProc.exitCode !== null) {
    return { ok: true, running: false };
  }
  try { desktopClientProc.stdin.end(); } catch (_) {}
  try { process.kill(-desktopClientProc.pid, "SIGTERM"); } catch (_) {
    try { desktopClientProc.kill(); } catch (_2) {}
  }
  return { ok: true, running: false };
}

async function startDesktopClient(opts) {
  stopDesktopClient();
  const bin = resolveWhatCli();
  const host = String(opts?.host || "127.0.0.1");
  const port = String(opts?.port || 8765);
  const desktopClientId = "desktop-" + Math.random().toString(36).slice(2, 10);
  const args = [
    "client", "--local", "--captions-on",
    "--client-id", desktopClientId,
    "--input", "stdin",
    "--stdin-raw",
    "--no-mic",
    "--no-desktop",
    "--event-prefix", "EVENT:",
    "--host", host,
    "--port", port,
  ];
  if (process.env.WHAT_PYTHON && !process.env.WHAT_CLI) args.unshift("-m", "what");
  sendDesktopClientLog(`starting desktop: ${bin} ${args.join(" ")}\n`);
  const cwd = WHAT_PATHS.pythonRoot;

  // Linux (PulseAudio monitor) and Windows (WASAPI/DirectShow loopback) share the same
  // ffmpeg-PCM capture helper: it spawns `python -m what.desktop_capture`, whose backend is
  // resolved per platform, and pipes replay-suppressed PCM into the stdin client.
  if (process.platform === "linux" || process.platform === "win32") {
    const env = { ...process.env, TOKENIZERS_PARALLELISM: "false" };
    delete env.WHAT_CLIENT_ID;
    const python = runtimePaths.resolvePython({ pythonRoot: WHAT_PATHS.pythonRoot, env: process.env });
    linuxDesktopCapture = await require("./lib/linux_desktop_capture").startLinuxDesktopCapture({
      spawn, python, bin, args, cwd, env, suppressor: reviewSuppressor,
      log: sendDesktopClientLog, device: opts?.desktopDevice || "default",
    });
    desktopClientProc = linuxDesktopCapture.client;
    return { ok: true, running: true };
  }
  if (process.platform !== "darwin") throw new Error("Desktop capture is unsupported on this platform");

  desktopTapSocketPath = "/tmp/what-coreaudio-tap.sock";
  const tapApp = resolveTapApp();
  const tapBinInApp = path.join(tapApp, "Contents", "MacOS", "WhatCoreAudioTap");

  let connectedToExisting = false;
  try {
    desktopTapSocket = await connectToTapSocket(desktopTapSocketPath, 1200);
    sendDesktopClientLog("[tap] connected to existing tap instance\n");
    connectedToExisting = true;
  } catch (_) {}

  if (!connectedToExisting) {
    desktopTapLaunchedByUs = true;
    if (fs.existsSync(tapBinInApp)) {
      sendDesktopClientLog("[tap] launching via open -n\n");
      const opener = spawn("open", ["-n", tapApp, "--args", "--socket-path", desktopTapSocketPath, ...tapOwnerArgs()],
        { detached: true, stdio: "ignore" });
      opener.unref();
    } else {
      const tapBin = resolveTapBin();
      sendDesktopClientLog(`[tap] launching fallback: ${tapBin}\n`);
      const tp = spawn(tapBin, ["--socket-path", desktopTapSocketPath, ...tapOwnerArgs()],
        { detached: true, stdio: "ignore" });
      tp.unref();
    }
    try {
      desktopTapSocket = await connectToTapSocket(desktopTapSocketPath, 10000);
      sendDesktopClientLog("[tap] socket connected\n");
    } catch (err) {
      sendDesktopClientLog(`[tap] failed to connect: ${err.message}\n`);
    }
  }

  if (desktopTapSocket) {
    desktopTapSocket.on("error", err => sendDesktopClientLog(`[tap] socket error: ${err.message}\n`));
    desktopTapSocket.on("close", tryReconnectDesktopTapSocket);
  }

  const desktopClientEnv = { ...process.env, TOKENIZERS_PARALLELISM: "false" };
  delete desktopClientEnv.WHAT_CLIENT_ID; // prevent duplicate_client_id when env sets a fixed ID
  desktopClientProc = spawn(bin, args, {
    env: desktopClientEnv,
    cwd,
    detached: true,
  });

  if (desktopTapSocket) {
    reviewSuppressor.pipeTapToClient(desktopTapSocket, desktopClientProc.stdin);
  }

  desktopClientProc.stdout.on("data", d => sendDesktopClientLog(d.toString()));
  desktopClientProc.stderr.on("data", d => sendDesktopClientLog(d.toString()));
  desktopClientProc.on("error", err => sendDesktopClientLog(`desktop client error: ${err.message}\n`));
  desktopClientProc.on("exit", (code, signal) =>
    sendDesktopClientLog(`desktop client exited (${signal || code})\n`)
  );

  return { ok: true, running: true };
}

function desktopClientStatus() {
  return { running: Boolean(desktopClientProc && desktopClientProc.exitCode === null) };
}

let clientMutation = Promise.resolve();
function mutateClient(operation) {
  const result = clientMutation.catch(() => {}).then(operation);
  clientMutation = result;
  return result;
}
ipcMain.handle("client-start", (_event, opts) => mutateClient(() => startClient(opts)));
ipcMain.handle("client-stop", () => mutateClient(() => stopClient()));
ipcMain.handle("client-status", () => clientStatus());
let desktopMutation = Promise.resolve();
function mutateDesktop(operation) {
  const result = desktopMutation.then(operation, operation);
  desktopMutation = result.catch(() => {});
  return result;
}
ipcMain.handle("desktop-client-start", (_event, opts) => mutateDesktop(() => startDesktopClient(opts)));
ipcMain.handle("resolve-recording", (_event, opts) => {
  const result = reviewAudio.resolveRecording({
    logsDir: SERVICE_LOGS_DIR,
    sessionId: opts && opts.sessionId,
    clientId: opts && opts.clientId,
  });
  return result.ok ? { ...result, url: pathToFileURL(result.path).href } : result;
});
ipcMain.handle("audio-defaults", () => audioDefaults.readDefaultDevices());
ipcMain.handle("save-session-correction", (_event, correction) =>
  sessionCorrections.appendSessionCorrection({ logsDir: SERVICE_LOGS_DIR, correction })
);
ipcMain.handle("set-review-playback", (_event, opts) =>
  reviewSuppressor.setActive(Boolean(opts && opts.active), opts && opts.maxMs)
);
ipcMain.handle("desktop-client-stop", () => mutateDesktop(() => stopDesktopClient()));
ipcMain.handle("desktop-client-status", () => desktopClientStatus());

ipcMain.handle("list-mic-devices", () => {
  try {
    return { ok: true, devices: micDevices.listMicDevices({ spawnSync }) };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});
ipcMain.handle("tap-setup-ensure", async (event) =>
  ensureTapSetup(line => event.sender.send("tap-setup-log", line))
);
ipcMain.handle("tap-open-screen-permissions", () => {
  if (process.platform !== "darwin") return { ok: false, error: "macOS only" };
  shell.openExternal("x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture");
  return { ok: true };
});
ipcMain.handle("open-desktop-audio-stub", () => {
  createDesktopAudioStubWindow();
  return { ok: true };
});
fileIpcHandlers.registerFileIpcHandlers({
  ipcMain,
  dialog,
  fs,
  path,
  baseDir: __dirname
});

desktopIpcHandlers.registerDesktopIpcHandlers({
  ipcMain,
  app,
  path,
  baseDir: __dirname,
  desktopAudioProbe,
  desktopAudioManager,
  audioRoutingManager
});

correctionsIpcHandlers.registerCorrectionsIpcHandlers({
  ipcMain,
  fs,
  path,
  baseDir: __dirname,
  spawnSync,
  env: process.env
});

overlayIpcHandlers.registerOverlayIpcHandlers({
  ipcMain,
  normalizeOverlayPayload,
  getOverlayPayload: () => overlayPayload,
  setOverlayPayload: (next) => { ingestOverlayPayload(next); },
  overlayClients,
  overlayPayloadForBox,
  encodeOverlay: _encodeOverlay,
  getOverlayPort: () => overlayServerRuntime.getPort(),
  getMainWindow: () => mainWindow,
  getOverlayTestStreamEnabled: () => localTestStreamRuntime.isEnabled(),
  setOverlayTestStreamEnabled
});

ipcMain.handle("get-ui-prefs", async () => loadUiPrefsDisk());
ipcMain.handle("set-ui-prefs", async (_event, prefs) => saveUiPrefsDisk(prefs));

function _encodeOverlay(payload) {
  return JSON.stringify(payload).replace(/\r?\n/g, "\\n");
}
