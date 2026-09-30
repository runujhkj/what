const { contextBridge, ipcRenderer } = require("electron");

const defaultBaseUrl = "http://127.0.0.1:8780";
const defaultTimeoutMs = 90000;

async function request(method, url, body, timeoutMs = defaultTimeoutMs) {
  const options = { method, headers: { "Content-Type": "application/json" } };
  if (body) {
    options.body = JSON.stringify(body);
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), Number(timeoutMs || defaultTimeoutMs));
  options.signal = controller.signal;
  let resp;
  try {
    resp = await fetch(url, options);
  } catch (err) {
    if (err && err.name === "AbortError") {
      throw new Error(`request timeout after ${timeoutMs}ms`);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`HTTP ${resp.status}: ${text}`);
  }
  return resp.json();
}

contextBridge.exposeInMainWorld("whatControl", {
  status: (baseUrl) => request("GET", `${baseUrl || defaultBaseUrl}/control/status`, undefined, 7000),
  gpu: (baseUrl) => request("GET", `${baseUrl || defaultBaseUrl}/control/gpu`),
  start: (baseUrl, payload) => request("POST", `${baseUrl || defaultBaseUrl}/control/start`, payload),
  apply: (baseUrl, payload) => request("POST", `${baseUrl || defaultBaseUrl}/control/apply`, payload),
  setSettings: (baseUrl, payload) =>
    request("POST", `${baseUrl || defaultBaseUrl}/control/settings`, payload && typeof payload === "object" ? payload : {}),
  stop: (baseUrl) => request("POST", `${baseUrl || defaultBaseUrl}/control/stop`, {}),
  setPublishDelay: (baseUrl, seconds) =>
    request("POST", `${baseUrl || defaultBaseUrl}/control/publish-delay`, {
      publish_delay_seconds: Number(seconds)
    }),
  setOverlayGeometry: (baseUrl, payload) =>
    request("POST", `${baseUrl || defaultBaseUrl}/control/overlay-geometry`, payload || {}),
  sessionLog: (baseUrl, message) =>
    request("POST", `${baseUrl || defaultBaseUrl}/control/session/log`, { message: String(message || "") }),
  streamLogs: (baseUrl, offset) =>
    request("GET", `${baseUrl || defaultBaseUrl}/control/stream/logs?offset=${Number(offset || 0)}`),
  streamEvents: (baseUrl, offset) =>
    request("GET", `${baseUrl || defaultBaseUrl}/control/stream/events?offset=${Number(offset || 0)}`),
  setStreamSettings: (baseUrl, payload) =>
    request("POST", `${baseUrl || defaultBaseUrl}/control/stream/settings`, payload && typeof payload === "object" ? payload : {}),
  streamStart: (baseUrl, payload) =>
    request("POST", `${baseUrl || defaultBaseUrl}/control/stream/start`, payload && typeof payload === "object" ? payload : {}),
  streamStop: (baseUrl, payload) =>
    request("POST", `${baseUrl || defaultBaseUrl}/control/stream/stop`, payload && typeof payload === "object" ? payload : {}),
  desktopAudioApiStatus: (baseUrl, options) => {
    const opts = options && typeof options === "object" ? options : {};
    const includeRouting = opts.includeRouting === true;
    const qs = includeRouting ? "?include_routing=1" : "?include_routing=0";
    return request("GET", `${baseUrl || defaultBaseUrl}/control/desktop-audio/status${qs}`, undefined, 7000);
  },
  desktopAudioApiInstall: (baseUrl, payload) =>
    request(
      "POST",
      `${baseUrl || defaultBaseUrl}/control/desktop-audio/install`,
      payload && typeof payload === "object" ? payload : {},
      240000
    ),
  desktopAudioApiUninstall: (baseUrl) =>
    request("POST", `${baseUrl || defaultBaseUrl}/control/desktop-audio/uninstall`, {}, 240000),
  desktopAudioApiPing: (baseUrl, payload) =>
    request(
      "POST",
      `${baseUrl || defaultBaseUrl}/control/desktop-audio/ping`,
      payload && typeof payload === "object" ? payload : {},
      12000
    ),
  clientStart: (opts) => ipcRenderer.invoke("client-start", opts),
  clientStop: () => ipcRenderer.invoke("client-stop"),
  clientStatus: () => ipcRenderer.invoke("client-status"),
  desktopClientStart: (opts) => ipcRenderer.invoke("desktop-client-start", opts),
  desktopClientStop: () => ipcRenderer.invoke("desktop-client-stop"),
  desktopClientStatus: () => ipcRenderer.invoke("desktop-client-status"),
  transcriptCleanup: (text) =>
    request("POST", `${defaultBaseUrl}/control/cleanup`, { text: String(text || "") }, 120000),
  tapSetupEnsure: () => ipcRenderer.invoke("tap-setup-ensure"),
  tapOpenScreenPermissions: () => ipcRenderer.invoke("tap-open-screen-permissions"),
  onTapSetupLog: (callback) => ipcRenderer.on("tap-setup-log", (_event, line) => callback(line)),
  openDesktopAudioStub: () => ipcRenderer.invoke("open-desktop-audio-stub"),
  onClientLog: (callback) => ipcRenderer.on("client-log", (_event, line) => callback(line)),
  onAppStatus: (callback) => ipcRenderer.on("app-status", (_event, message) => callback(message)),
  onDesktopClientLog: (callback) => ipcRenderer.on("desktop-client-log", (_event, line) => callback(line)),
  pickAudioFile: () => ipcRenderer.invoke("pick-audio-file"),
  listMicDevices: () => ipcRenderer.invoke("list-mic-devices"),
  resolveRecording: (sessionId, clientId) => ipcRenderer.invoke("resolve-recording", { sessionId, clientId }),
  setReviewPlayback: (active, maxMs) => ipcRenderer.invoke("set-review-playback", { active, maxMs }),
  saveSessionCorrection: (correction) => ipcRenderer.invoke("save-session-correction", correction),
  setSessionContext: (sessionId) => ipcRenderer.invoke("set-session-context", sessionId || null),
  sessionStopped: (sessionId) => ipcRenderer.invoke("session-stopped", sessionId),
  onSessionLoaded: (callback) => ipcRenderer.on("session-loaded", (_event, payload) => callback(payload)),
  onSessionNew: (callback) => ipcRenderer.on("session-new", () => callback()),
  getAudioDefaults: () => ipcRenderer.invoke("audio-defaults"),
  listAudioFiles: () => ipcRenderer.invoke("list-audio-files"),
  listDesktopDevices: (backend) => ipcRenderer.invoke("list-desktop-devices", backend),
  desktopAudioManagerStatus: () => ipcRenderer.invoke("desktop-audio-manager-status"),
  desktopAudioManagerDownload: () => ipcRenderer.invoke("desktop-audio-manager-download"),
  desktopAudioManagerInstall: () => ipcRenderer.invoke("desktop-audio-manager-install"),
  desktopAudioManagerUninstall: () => ipcRenderer.invoke("desktop-audio-manager-uninstall"),
  desktopAudioManagerReloadAudio: () => ipcRenderer.invoke("desktop-audio-manager-reload-audio"),
  audioRoutingStatus: () => ipcRenderer.invoke("audio-routing-status"),
  audioRoutingApply: () => ipcRenderer.invoke("audio-routing-apply"),
  audioRoutingRestore: () => ipcRenderer.invoke("audio-routing-restore"),
  appendCorrection: (payload) => ipcRenderer.invoke("append-correction", payload),
  exportCorrectionsMeta: (payload) => ipcRenderer.invoke("export-corrections-meta", payload),
  exportCorrectionsBundle: (payload) => ipcRenderer.invoke("export-corrections-bundle", payload),
  importCorrectionsBundle: (payload) => ipcRenderer.invoke("import-corrections-bundle", payload),
  pickCorrectionsBundle: () => ipcRenderer.invoke("pick-corrections-bundle"),
  pickObsOutput: () => ipcRenderer.invoke("pick-obs-output"),
  writeObsOutput: (payload) => ipcRenderer.invoke("write-obs-output", payload),
  setOverlayText: (payload) => ipcRenderer.invoke("set-overlay-text", payload),
  getOverlayUrl: () => ipcRenderer.invoke("get-overlay-url"),
  setTestStream: (enabledOrConfig) => ipcRenderer.invoke("set-test-stream", enabledOrConfig),
  getUiPrefs: () => ipcRenderer.invoke("get-ui-prefs"),
  setUiPrefs: (prefs) => ipcRenderer.invoke("set-ui-prefs", prefs || {}),
  onExternalTestStream: (callback) =>
    ipcRenderer.on("external-test-stream", (_event, enabled) => callback(Boolean(enabled)))
});
