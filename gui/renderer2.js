// ── Utilities ─────────────────────────────────────────────────────────────────

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const CTRL = window.whatControl;
const BASE_URL = "http://127.0.0.1:8780";
const inputSwitches = window.whatDeviceSwitching.createSwitchQueue();
const outputSwitches = window.whatDeviceSwitching.createSwitchQueue();
let savedPlaybackDevice = "default";

// ── State ─────────────────────────────────────────────────────────────────────

const state = {
  phase: "idle",       // "idle" | "starting" | "running" | "stopping"
  sourceMic: true,
  sourceDesktop: false,
  profile: "captions",
  delay: 0,
  noVad: false,
  gpuBudgetMb: 0,      // total VRAM cap for the Whisper workers; 0 = no limit
};

// Retained transcript for the current session (each Start begins a new service
// session): full segment records with identity, word timing and audio availability,
// kept independently of the short live caption window. Not capped.
const transcript = window.whatGuiTranscriptRecord.createTranscriptStore();

// Live controller status from the last poll.
let lastStatus = null;

// ── Transitions ───────────────────────────────────────────────────────────────

function transition(action, payload) {
  switch (action) {
    case "RESTORE":
      if (typeof payload.sourceMic === "boolean") state.sourceMic = payload.sourceMic;
      if (typeof payload.sourceDesktop === "boolean") state.sourceDesktop = payload.sourceDesktop;
      if (payload.profile) state.profile = String(payload.profile);
      if (typeof payload.delay === "number") state.delay = payload.delay;
      if (typeof payload.noVad === "boolean") state.noVad = payload.noVad;
      if (Number.isFinite(payload.gpuBudgetMb) && payload.gpuBudgetMb >= 0) state.gpuBudgetMb = payload.gpuBudgetMb;
      break;
    case "STARTING":
      state.phase = "starting";
      stopReplay();
      transcript.clear();
      for (const panel of Object.values(panels)) panel.clear();
      captionBridge.start();
      break;
    case "STARTED":
      state.phase = "running";
      break;
    case "STOPPING":
      state.phase = "stopping";
      captionBridge.stop();
      break;
    case "STOPPED":
      state.phase = "idle";
      break;
    case "ERROR":
      captionBridge.stop();
      state.phase = "idle";
      break;
    case "TOGGLE_MIC":
      if (state.phase !== "idle") return;
      state.sourceMic = !state.sourceMic;
      break;
    case "TOGGLE_DESKTOP":
      if (state.phase !== "idle") return;
      state.sourceDesktop = !state.sourceDesktop;
      break;
    case "SET_PROFILE":
      state.profile = String(payload || "");
      break;
    case "SET_DELAY":
      state.delay = Number(payload) || 0;
      break;
    case "SET_NO_VAD":
      state.noVad = Boolean(payload);
      break;
    case "SET_GPU_BUDGET":
      state.gpuBudgetMb = Math.max(0, Number(payload) || 0);
      break;
    default:
      return;
  }
  render();
}

// ── DOM ───────────────────────────────────────────────────────────────────────

const dom = {
  controllerDot: document.getElementById("controllerDot"),
  controllerLabel: document.getElementById("controllerLabel"),
  startStopBtn: document.getElementById("startStopBtn"),
  statusLine: document.getElementById("statusLine"),
  micBtn: document.getElementById("micBtn"),
  desktopBtn: document.getElementById("desktopBtn"),
  transcriptSection: document.getElementById("transcriptSection"),
  micPanel: document.getElementById("micPanel"),
  desktopPanel: document.getElementById("desktopPanel"),
  micTranscriptOut: document.getElementById("micTranscriptOut"),
  desktopTranscriptOut: document.getElementById("desktopTranscriptOut"),
  micReturnLive: document.getElementById("micReturnLive"),
  desktopReturnLive: document.getElementById("desktopReturnLive"),
  replayBar: document.getElementById("replayBar"),
  replayLabel: document.getElementById("replayLabel"),
  replayStopBtn: document.getElementById("replayStopBtn"),
  micModeSelect: document.getElementById("micModeSelect"),
  micDeviceField: document.getElementById("micDeviceField"),
  micFileField: document.getElementById("micFileField"),
  micDeviceSelect: document.getElementById("micDeviceSelect"),
  playbackDeviceSelect: document.getElementById("playbackDeviceSelect"),
  refreshPlaybackBtn: document.getElementById("refreshPlaybackBtn"),
  refreshMicBtn: document.getElementById("refreshMicBtn"),
  micFileSelect: document.getElementById("micFileSelect"),
  browseMicFileBtn: document.getElementById("browseMicFileBtn"),
  profileInput: document.getElementById("profileInput"),
  delayInput: document.getElementById("delayInput"),
  noVadInput: document.getElementById("noVadInput"),
  gpuBudgetField: document.getElementById("gpuBudgetField"),
  gpuBudgetSelect: document.getElementById("gpuBudgetSelect"),
  gpuBudgetHint: document.getElementById("gpuBudgetHint"),
  desktopSetupBtn: document.getElementById("desktopSetupBtn"),
  debugOut: document.getElementById("debugOut"),
};

// ── Render ────────────────────────────────────────────────────────────────────

function render() {
  const { phase, sourceMic, sourceDesktop, profile, delay, noVad, gpuBudgetMb } = state;
  const idle = phase === "idle";
  const running = phase === "running";
  const busy = phase === "starting" || phase === "stopping";
  const canStart = idle && (sourceMic || sourceDesktop) && !!profile.trim();

  dom.startStopBtn.disabled = busy || (idle && !canStart);
  dom.startStopBtn.className = running ? "running" : busy ? phase : "";
  dom.startStopBtn.textContent = running ? "Stop" : busy ? "…" : "Start";

  dom.micDeviceSelect.disabled = busy;
  dom.micModeSelect.disabled = !idle;
  dom.micBtn.disabled = !idle;
  dom.desktopBtn.disabled = !idle;
  dom.micBtn.className = "source-btn" + (sourceMic ? " active-mic" : "");
  dom.desktopBtn.className = "source-btn" + (sourceDesktop ? " active-desktop" : "");

  dom.profileInput.value = profile;
  dom.delayInput.value = delay;
  dom.noVadInput.checked = noVad;
  setGpuBudgetSelect(gpuBudgetMb);
  dom.gpuBudgetSelect.disabled = !idle;

  // Show/hide transcript panels based on active sources.
  // In running or stopping phase, use the sources that are actually active.
  // In idle/starting phase, use current toggle state to preview layout.
  const showMic = sourceMic;
  const showDesktop = sourceDesktop;
  const dual = showMic && showDesktop;

  dom.micPanel.style.display = showMic ? "" : "none";
  dom.desktopPanel.style.display = showDesktop ? "" : "none";
  dom.transcriptSection.classList.toggle("dual", dual);
}

// Keep a budget saved from another value (or set via prefs) selectable instead of
// silently snapping it to "No limit".
function setGpuBudgetSelect(mb) {
  const value = String(mb || 0);
  const options = Array.from(dom.gpuBudgetSelect.options || []);
  if (!options.some((o) => o.value === value) && typeof dom.gpuBudgetSelect.add === "function") {
    dom.gpuBudgetSelect.add(new Option(`${(Number(value) / 1024).toFixed(1)} GB`, value));
  }
  dom.gpuBudgetSelect.value = value;
}

// Apple Silicon runs WhisperKit (no CUDA), so the VRAM cap has nothing to limit there.
async function initGpuBudgetField() {
  if (/^Mac/i.test(navigator.platform || "")) {
    dom.gpuBudgetField.style.display = "none";
    return;
  }
  try {
    const gpu = await CTRL.gpu(BASE_URL);
    const card = gpu && Array.isArray(gpu.gpus) ? gpu.gpus[0] : null;
    if (card && card.total_mb) {
      dom.gpuBudgetHint.textContent = `${card.name}: ${(card.total_mb / 1024).toFixed(1)} GB total, `
        + `${(card.used_mb / 1024).toFixed(1)} GB in use now. Applies at the next Start: the largest `
        + "speech model that fits is used, or the CPU if none does.";
    } else if (gpu && !gpu.available) {
      dom.gpuBudgetHint.textContent = "No CUDA GPU detected; transcription runs on the CPU.";
    }
  } catch (_) {}
}

function setStatus(msg, isError) {
  dom.statusLine.textContent = msg;
  dom.statusLine.className = isError ? "error" : "";
}

let controllerUp = false;
let appStatusMessage = null;
if (typeof CTRL.onAppStatus === "function") {
  CTRL.onAppStatus((message) => {
    appStatusMessage = message || null;
    if (!controllerUp && state.phase === "idle") {
      setStatus(appStatusMessage || "controller not reachable", !appStatusMessage);
    }
  });
}

function setControllerState(up) {
  const wasUp = controllerUp;
  controllerUp = up;
  dom.controllerDot.className = up ? "up" : "";
  dom.controllerLabel.textContent = up ? "controller ready" : "controller";
  if (up && !wasUp && state.phase === "idle") {
    dom.startStopBtn.disabled = false;
    setStatus("idle");
  }
  if (up && !wasUp) initGpuBudgetField();
  if (!up && state.phase === "idle") {
    dom.startStopBtn.disabled = true;
    // While the packaged app prepares itself (e.g. a first-run GPU download) say so,
    // rather than reporting an error.
    if (appStatusMessage) setStatus(appStatusMessage);
    else setStatus("controller not reachable", true);
  }
}

function appendDebug(line) {
  dom.debugOut.textContent += line + "\n";
  dom.debugOut.scrollTop = dom.debugOut.scrollHeight;
}

// ── Transcript ────────────────────────────────────────────────────────────────

// Keep stdout framing and publication independent from the transcript display.
const captionBridge = window.whatGuiLiveCaptionBridge.createLiveCaptionBridge({
  send: (payload) => CTRL.setOverlayText(payload),
  getDelaySeconds: () => state.delay,
  onError: (error) => appendDebug(`overlay publication failed: ${error.message || error}`),
  onEvent: (event, source) => {
    const added = transcript.ingest(event, source);
    if (added.length) panels[source === "desktop" ? "desktop" : "mic"].append(added);
  },
});

function ingestClientChunk(chunk, source) {
  captionBridge.ingest(chunk, source);
}

function createPanel(source, container, returnBtn) {
  const panel = window.whatGuiTranscriptView.createTranscriptPanel({
    document,
    container,
    store: transcript,
    onSeekClick: (hit) => { startReplay(source, hit).catch((err) => setStatus(`replay failed: ${err.message || err}`, true)); },
    onEditCommit: (key, text) => saveCorrection(source, key, text),
    onFollowChange: ({ follow, pendingNew }) => {
      returnBtn.hidden = follow;
      returnBtn.textContent = pendingNew > 0 ? `Return to live (${pendingNew} new)` : "Return to live";
    },
  });
  returnBtn.addEventListener("click", () => panel.returnToLive());
  return panel;
}

const panels = {
  mic: createPanel("mic", dom.micTranscriptOut, dom.micReturnLive),
  desktop: createPanel("desktop", dom.desktopTranscriptOut, dom.desktopReturnLive),
};

// ── Corrections ───────────────────────────────────────────────────────────────
//
// A correction is saved (logs/<session>/corrections.jsonl, next to the recording) before
// it becomes the segment's displayed revision, so the transcript never shows an edit that
// was not recorded. Recognition output and word timing stay unchanged in the record.

async function saveCorrection(source, key, text) {
  const record = transcript.get(key);
  if (!record) return;
  const correction = transcript.buildCorrection(record, text);
  if (!correction) return; // unchanged
  let result;
  try {
    result = await CTRL.saveSessionCorrection(correction);
  } catch (err) {
    result = { ok: false, error: err.message || String(err) };
  }
  if (!result || !result.ok) {
    setStatus(`correction not saved: ${(result && result.error) || "unknown error"}`, true);
    return;
  }
  transcript.applyCorrection(record, correction);
  const audioNote = correction.audio.available ? "" : ` (no audio: ${correction.audio.reason})`;
  setStatus(`correction saved to ${source} transcript${audioNote}`);
}

// ── Replay ────────────────────────────────────────────────────────────────────
//
// Modifier-click a word to replay that source's recording from it. Recordings are read
// from the local service's logs directory via the main process. While playing, the main
// process silences desktop tap audio so the replay isn't transcribed as new desktop
// speech. Transcript review stays separate from live caption publication.

const REPLAY_UNAVAILABLE = {
  not_recorded: "audio was not recorded for this segment",
  recording_status_unknown: "this segment's service did not report a recording, so audio is unavailable",
  no_timing: "this segment has no timing, so it cannot be replayed",
  unknown_segment: "that segment is no longer in the transcript",
  recording_missing: "recording not found in the local logs folder (a service on another machine is not supported yet)",
  recording_unreadable: "the recording file could not be read",
  invalid_id: "this segment's recording identity is invalid",
  not_yet_written: "that audio has not been written to the recording yet",
};

function replayUnavailable(reason) {
  setStatus(`can't replay: ${REPLAY_UNAVAILABLE[reason] || reason || "unknown reason"}`, true);
}

let replay = null; // { audio, source, key }
let replayGeneration = 0;

async function startReplay(source, { key, wordIndex }) {
  stopReplay();
  const generation = replayGeneration;
  try {
    const target = transcript.seekTarget(transcript.get(key), wordIndex);
    if (!target.ok) { replayUnavailable(target.reason); return; }
    const recording = await CTRL.resolveRecording(target.sessionId, target.clientId);
    if (generation !== replayGeneration) return;
    if (!recording || !recording.ok) { replayUnavailable(recording && recording.reason); return; }
    if (target.start >= recording.durationSec) { replayUnavailable("not_yet_written"); return; }

    // A recording grows during capture. Give each replay a fresh resource identity
    // so Chromium cannot reuse the first click's WAV header/duration and byte ranges.
    const separator = recording.url.includes("?") ? "&" : "?";
    const audio = new Audio(`${recording.url}${separator}replay=${generation}`);
    replay = { audio, source, key };
    await new Promise((resolve, reject) => {
      audio.addEventListener("loadedmetadata", resolve, { once: true });
      audio.addEventListener("error", () => reject(new Error("could not load the recording")), { once: true });
    });
    if (!replay || replay.audio !== audio) return; // superseded while loading
    audio.currentTime = target.start;
    const endIfCurrent = () => { if (replay && replay.audio === audio) stopReplay(); };
    audio.addEventListener("ended", endIfCurrent);
    audio.addEventListener("error", endIfCurrent);
    // Silence desktop capture before any audio is audible; it expires on its own after
    // the remaining recording length in case this window goes away mid-replay.
    const remainingMs = (recording.durationSec - target.start) * 1000;
    await CTRL.setReviewPlayback(true, remainingMs + 2000);
    if (!replay || replay.audio !== audio) return;
    await outputSwitches.run(async () => {
      await window.whatDeviceSwitching.routePlayback(audio, savedPlaybackDevice);
      if (!replay || replay.audio !== audio) return;
    }, { coalesce: false });
    if (!replay || replay.audio !== audio) return;
    // Playback can remain pending while media loads. Do not hold the output-device
    // queue hostage: a later click must be able to route and start its own audio.
    await audio.play();
    if (!replay || replay.audio !== audio) return;
    panels[source].setPlaying(key);
    const at = target.precision === "word" ? "" : " (segment start)";
    dom.replayLabel.textContent = `▶ Replaying ${source} from ${target.start.toFixed(1)}s${at}`;
    dom.replayBar.hidden = false;
  } catch (err) {
    if (generation !== replayGeneration) return;
    stopReplay();
    throw err;
  }
}

function stopReplay() {
  replayGeneration += 1;
  if (!replay) return;
  const { audio, source } = replay;
  replay = null;
  try { audio.pause(); } catch (_) {}
  audio.removeAttribute("src");
  // Reset the media resource and abort pending play/load operations, not just sound.
  audio.load();
  panels[source].setPlaying(null);
  dom.replayBar.hidden = true;
  CTRL.setReviewPlayback(false, 0).catch(() => {});
}

dom.replayStopBtn.addEventListener("click", stopReplay);
// While Cmd/Ctrl is held, words show as replay targets (see .seek-mod in index2.html).
function setSeekModifier(on) {
  if (document.body) document.body.classList.toggle("seek-mod", Boolean(on));
}
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && replay) stopReplay();
  setSeekModifier(event.metaKey || event.ctrlKey);
});
document.addEventListener("keyup", (event) => setSeekModifier(event.metaKey || event.ctrlKey));
window.addEventListener("blur", () => setSeekModifier(false));

// ── Service wait ──────────────────────────────────────────────────────────────

// Service start time varies widely: ~5 s warm, but the first start after installing can
// take much longer while Windows scans the freshly installed libraries (a 12 s limit
// failed exactly then). Wait generously, but stop at once if the service process exits.
async function waitForService(host, port, timeoutMs = 120000) {
  const url = `http://${host}:${port}/health`;
  const started = Date.now();
  let lastErr = null;
  let slowNoticeShown = false;
  let nextAliveCheck = started + 2000;
  while (Date.now() - started < timeoutMs) {
    try {
      const r = await fetch(url);
      if (r.ok) return;
    } catch (err) { lastErr = err; }
    if (!slowNoticeShown && Date.now() - started > 8000) {
      slowNoticeShown = true;
      setStatus("starting Whisper service… (the first start after installing can take a minute)");
    }
    if (Date.now() >= nextAliveCheck) {
      nextAliveCheck = Date.now() + 2000;
      try {
        const st = await CTRL.status(BASE_URL);
        if (st && st.running === false) {
          throw new Error("the Whisper service exited during startup (see Debug for its output)");
        }
      } catch (err) {
        if (/exited during startup/.test(err.message)) throw err;
      }
    }
    await sleep(300);
  }
  throw new Error(`service not ready at ${host}:${port}: ${lastErr ? lastErr.message : "timeout"}`);
}

// Wait until port is NOT reachable (confirms old service has shut down).
async function waitForPortFree(host, port, timeoutMs = 5000) {
  const url = `http://${host}:${port}/health`;
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      await fetch(url, { signal: AbortSignal.timeout(400) });
      // Still reachable — keep waiting
      await sleep(250);
    } catch (_) {
      return; // port not reachable — we're good
    }
  }
  // Timed out — port may still be in use, but proceed anyway
}

// ── Start session ─────────────────────────────────────────────────────────────

let _starting = false;

// Latest dead-input warning from the mic client; kept visible over later status updates.
let micCaptureWarning = null;
// Output-device change seen while this session started (see lib/output_watch.js).
let outputChangeNotice = null;
const outputWatch = window.whatGuiOutputWatch.createOutputWatch({
  read: () => (typeof CTRL.getAudioDefaults === "function"
    ? CTRL.getAudioDefaults()
    : Promise.resolve({ ok: false, error: "unavailable" })),
  onChange: (change) => {
    outputChangeNotice = window.whatGuiOutputWatch.describeOutputChange(change);
    appendDebug(`[audio] ${outputChangeNotice}`);
    setStatus(outputChangeNotice, true);
  },
});

async function startSession() {
  if (_starting) return;
  _starting = true;
  micCaptureWarning = null;
  outputChangeNotice = null;
  // The baseline read (~0.3 s) runs alongside service startup rather than delaying it.
  const outputSession = outputWatch.start().catch(() => ({ mark() {} }));
  const markStep = (label) => { outputSession.then((s) => s.mark(label)); };
  transition("STARTING");
  setStatus("starting…");

  const profile = dom.profileInput.value.trim();
  const delay = Number(dom.delayInput.value) || 0;
  const noVad = dom.noVadInput.checked;
  const gpuBudgetMb = Math.max(0, Number(dom.gpuBudgetSelect.value) || 0);
  const useMic = state.sourceMic;
  const useDesktop = state.sourceDesktop;

  state.profile = profile;
  state.delay = delay;
  state.noVad = noVad;

  if (!profile) {
    setStatus("profile is required — enter a profile name in Settings", true);
    transition("ERROR");
    _starting = false;
    return;
  }

  try {
    // Flush any stale Whisper service and wait for the port to actually free.
    setStatus("stopping any stale service…");
    try { await CTRL.stop(BASE_URL); } catch (_) {}
    await waitForPortFree("127.0.0.1", 8765, 4000);

    setStatus("starting Whisper service…");
    markStep("starting the Whisper service");
    await CTRL.start(BASE_URL, {
      profile,
      no_vad: noVad,
      publish_delay_seconds: delay,
      gpu_mem_budget_mb: gpuBudgetMb,
    });

    let host = "127.0.0.1";
    let port = 8765;
    try {
      const st = await CTRL.status(BASE_URL);
      lastStatus = st;
      if (st && st.service_host) host = st.service_host === "0.0.0.0" ? "127.0.0.1" : st.service_host;
      if (st && st.service_port) port = Number(st.service_port);
    } catch (_) {}

    setStatus("waiting for Whisper service…");
    await waitForService(host, port);

    if (useDesktop) {
      setStatus("setting up desktop tap…");
      const tapResult = await CTRL.tapSetupEnsure();
      if (tapResult && tapResult.needsPermission) {
        await CTRL.tapOpenScreenPermissions();
        setStatus("screen recording permission needed — grant in System Settings, then try again", true);
        transition("ERROR");
        _starting = false;
        return;
      }
    }

    if (useMic) {
      setStatus("connecting mic client…");
      const micLabel = dom.micModeSelect.value === "file"
        ? "reading the audio file"
        : `opening the microphone (${dom.micDeviceSelect.value === "default" || !dom.micDeviceSelect.value
          ? "System default input" : dom.micDeviceSelect.value})`;
      markStep(micLabel);
      const micMode = dom.micModeSelect.value; // "mic" | "file"
      // Always pass a device so a stale WHAT_MIC_DEVICE index in .env can't win.
      const micDevice = micMode === "mic" ? (dom.micDeviceSelect.value || "default") : "";
      const filePath = micMode === "file" ? (dom.micFileSelect.value || "") : "";
      if (micMode === "file" && !filePath) {
        setStatus("select an audio file in Settings before starting", true);
        transition("ERROR");
        _starting = false;
        return;
      }
      await CTRL.clientStart({
        host,
        port,
        inputMode: micMode,
        micEnabled: micMode === "mic",
        desktopEnabled: false,
        eventPrefix: "EVENT:",
        forceRestart: true,
        micDevice,
        filePath,
      });
    }

    if (useDesktop) {
      setStatus("connecting desktop tap client…");
      markStep("starting desktop capture");
      await CTRL.desktopClientStart({ host, port });
    }

    transition("STARTED");
    const label = useMic && useDesktop ? "mic + desktop" : useMic ? "mic" : "desktop";
    if (micCaptureWarning) setStatus(micCaptureWarning, true);
    else if (outputChangeNotice) setStatus(outputChangeNotice, true);
    else setStatus(`running (${label})`);

  } catch (err) {
    try { await CTRL.clientStop(); } catch (_) {}
    try { await CTRL.desktopClientStop(); } catch (_) {}
    setStatus(err.message || String(err), true);
    transition("ERROR");
    appendDebug(`start error: ${err.message || err}`);
  } finally {
    _starting = false;
  }
}

// ── Stop session ──────────────────────────────────────────────────────────────

async function stopSession() {
  outputWatch.stop();
  transition("STOPPING");
  stopReplay();
  setStatus("stopping…");

  await inputSwitches.cancel();
  let stopFailure = null;
  try { await CTRL.clientStop(); } catch (err) { stopFailure = err; }
  try { await CTRL.desktopClientStop(); } catch (_) {}
  try { await CTRL.stop(BASE_URL); } catch (_) {}

  transition("STOPPED");
  if (stopFailure) setStatus(`microphone stop failed: ${stopFailure.message || stopFailure}`, true);
  else setStatus("idle");
}

// ── Status polling ────────────────────────────────────────────────────────────

let statusPollTimer = null;

function startStatusPoll() {
  if (statusPollTimer) return;
  statusPollTimer = setInterval(pollStatus, 500);
  pollStatus();
}

let lastDefaultDeviceRead = 0;
let readingDefaultDevices = false;
const trackDefaultInput = window.whatDeviceSwitching.createDefaultInputTracker(() => {
  if (savedMicDevice === "default") switchLiveInput();
}, () => {
  // Changing system output can reconfigure a duplex Bluetooth/USB input even when
  // its name stays the same. Reopen the chosen input against the same service.
  switchLiveInput();
});
async function pollStatus() {
  if (!readingDefaultDevices && Date.now() - lastDefaultDeviceRead > 3000 && typeof CTRL.getAudioDefaults === "function") {
    readingDefaultDevices = true;
    lastDefaultDeviceRead = Date.now();
    Promise.resolve().then(() => CTRL.getAudioDefaults()).then(trackDefaultInput).catch(() => {})
      .finally(() => { readingDefaultDevices = false; });
  }
  try {
    lastStatus = await CTRL.status(BASE_URL);
    setControllerState(true);
  } catch (_) {
    setControllerState(false);
  }
}

// ── Prefs ─────────────────────────────────────────────────────────────────────

async function loadPrefs() {
  try {
    const prefs = await CTRL.getUiPrefs();
    if (prefs && typeof prefs === "object") {
      transition("RESTORE", {
        sourceMic: prefs.sourceMic,
        sourceDesktop: prefs.sourceDesktop,
        profile: prefs.profile2 || prefs.profile,
        delay: typeof prefs.delay2 === "number" ? prefs.delay2 : undefined,
        // noVad3 supersedes noVad2, which saved the former VAD-off default.
        noVad: prefs.noVad3,
        gpuBudgetMb: prefs.gpuBudgetMb,
      });
      if (typeof prefs.micDevice2 === "string") savedMicDevice = prefs.micDevice2;
      if (typeof prefs.playbackDevice === "string") savedPlaybackDevice = prefs.playbackDevice;
    }
  } catch (_) {}
}

async function savePrefs() {
  try {
    await CTRL.setUiPrefs({
      sourceMic: state.sourceMic,
      sourceDesktop: state.sourceDesktop,
      profile2: state.profile,
      delay2: state.delay,
      noVad3: state.noVad,
      gpuBudgetMb: state.gpuBudgetMb,
      micDevice2: savedMicDevice,
      playbackDevice: savedPlaybackDevice,
    });
  } catch (_) {}
}

// ── Event wiring ──────────────────────────────────────────────────────────────

dom.startStopBtn.addEventListener("click", () => {
  if (state.phase === "running") stopSession();
  else if (state.phase === "idle") startSession();
});

dom.micBtn.addEventListener("click", () => {
  transition("TOGGLE_MIC");
  savePrefs();
});

dom.desktopBtn.addEventListener("click", () => {
  transition("TOGGLE_DESKTOP");
  savePrefs();
});

dom.profileInput.addEventListener("change", () => {
  transition("SET_PROFILE", dom.profileInput.value.trim());
  savePrefs();
});

dom.delayInput.addEventListener("change", () => {
  transition("SET_DELAY", Number(dom.delayInput.value) || 0);
  savePrefs();
});

dom.noVadInput.addEventListener("change", () => {
  transition("SET_NO_VAD", dom.noVadInput.checked);
  savePrefs();
});

dom.gpuBudgetSelect.addEventListener("change", () => {
  transition("SET_GPU_BUDGET", Number(dom.gpuBudgetSelect.value) || 0);
  savePrefs();
});

dom.desktopSetupBtn.addEventListener("click", () => {
  CTRL.openDesktopAudioStub().catch(() => {});
});

// Mic devices are chosen by name: avfoundation indexes shift whenever a device is
// added or removed, so a saved index can silently start pointing at a different
// (e.g. virtual, all-silent) input. The client resolves the name at capture time.
let savedMicDevice = "default";

async function refreshMicDevices() {
  dom.refreshMicBtn.textContent = "…";
  dom.refreshMicBtn.disabled = true;
  try {
    const result = await CTRL.listMicDevices();
    if (!result || !result.ok || !result.devices) return;
    while (dom.micDeviceSelect.options.length > 0) dom.micDeviceSelect.remove(0);
    dom.micDeviceSelect.add(new Option("System default input", "default"));
    const names = result.devices.map((d) => d.name);
    for (const name of names) dom.micDeviceSelect.add(new Option(name, name));
    // Keep a saved device that is currently unplugged selected rather than silently
    // capturing from a different one; starting will then report it as not found.
    if (savedMicDevice !== "default" && !names.includes(savedMicDevice)) {
      dom.micDeviceSelect.add(new Option(`${savedMicDevice} (not connected)`, savedMicDevice));
    }
    dom.micDeviceSelect.value = savedMicDevice;
  } catch (_) {
  } finally {
    dom.refreshMicBtn.textContent = "↺";
    dom.refreshMicBtn.disabled = false;
  }
}

dom.refreshMicBtn.addEventListener("click", async () => { await refreshMicDevices(); switchLiveInput(); });
dom.micDeviceSelect.addEventListener("change", () => {
  savedMicDevice = dom.micDeviceSelect.value || "default";
  savePrefs();
  switchLiveInput();
});

let switchingInput = false;
function switchLiveInput() {
  if (state.phase !== "running" || !state.sourceMic || dom.micModeSelect.value !== "mic") return;
  const device = savedMicDevice;
  inputSwitches.run(async (current) => {
    switchingInput = true;
    try {
      setStatus(`switching microphone to ${device}…`);
      await CTRL.clientStop();
      if (!current() || state.phase !== "running") return;
      const host = lastStatus?.service_host || "127.0.0.1";
      await CTRL.clientStart({
        host: host === "0.0.0.0" ? "127.0.0.1" : host,
        port: Number(lastStatus?.service_port) || 8765,
        inputMode: "mic", micEnabled: true, desktopEnabled: false,
        eventPrefix: "EVENT:", forceRestart: true, micDevice: device,
      });
      if (current() && state.phase === "running") setStatus(`microphone switched to ${device}; waiting for speech`);
    } finally { switchingInput = false; }
  }).catch(err => setStatus(`microphone switch failed: ${err.message || err}; choose a device to retry`, true));
}

let inputDeviceFingerprint = null;
async function refreshPlaybackDevices() {
  if (!navigator.mediaDevices?.enumerateDevices) return;
  const devices = await navigator.mediaDevices.enumerateDevices();
  const fingerprint = devices.filter(d => d.kind === "audioinput")
    .map(d => `${d.deviceId}:${d.groupId}:${d.label}`).sort().join("|");
  const inputChanged = inputDeviceFingerprint !== null && fingerprint !== inputDeviceFingerprint;
  inputDeviceFingerprint = fingerprint;
  const select = dom.playbackDeviceSelect;
  select.replaceChildren(new Option("System default output", "default"));
  for (const device of devices.filter(d => d.kind === "audiooutput" && d.deviceId && d.deviceId !== "default")) {
    select.add(new Option(device.label || `Output ${select.options.length}`, device.deviceId));
  }
  if (savedPlaybackDevice !== "default" && !devices.some(d => d.kind === "audiooutput" && d.deviceId === savedPlaybackDevice)) {
    select.add(new Option("Selected output (not connected)", savedPlaybackDevice));
    if (replay) { stopReplay(); setStatus("Playback output disconnected; choose an output to resume replay.", true); }
  }
  select.value = savedPlaybackDevice;
  if (inputChanged) { await refreshMicDevices(); switchLiveInput(); }
}
dom.refreshPlaybackBtn.addEventListener("click", () => refreshPlaybackDevices().catch(err => setStatus(err.message, true)));
dom.playbackDeviceSelect.addEventListener("change", () => {
  savedPlaybackDevice = dom.playbackDeviceSelect.value;
  savePrefs();
  const active = replay;
  outputSwitches.run(async () => {
    if (active && replay === active) await window.whatDeviceSwitching.routePlayback(active.audio, savedPlaybackDevice);
  }, { coalesce: false }).catch(err => {
    if (active && replay === active) {
      stopReplay(); setStatus(`playback output switch failed: ${err.message}; choose an output and replay again`, true);
    }
  });
});
let deviceRefreshTimer;
navigator.mediaDevices?.addEventListener("devicechange", () => {
  clearTimeout(deviceRefreshTimer);
  deviceRefreshTimer = setTimeout(() => refreshPlaybackDevices().catch(err => setStatus(err.message, true)), 250);
});

function updateMicModeVisibility() {
  const isFile = dom.micModeSelect.value === "file";
  dom.micDeviceField.style.display = isFile ? "none" : "";
  dom.micFileField.style.display = isFile ? "" : "none";
}

dom.micModeSelect.addEventListener("change", updateMicModeVisibility);

async function loadAudioFiles() {
  try {
    const files = await CTRL.listAudioFiles();
    if (!files || !files.length) return;
    const current = dom.micFileSelect.value;
    while (dom.micFileSelect.options.length > 1) dom.micFileSelect.remove(1);
    for (const f of files) {
      dom.micFileSelect.add(new Option(f.label, f.path));
    }
    if (current) dom.micFileSelect.value = current;
    if (!dom.micFileSelect.value) dom.micFileSelect.selectedIndex = 1;
  } catch (_) {}
}

dom.browseMicFileBtn.addEventListener("click", async () => {
  try {
    const picked = await CTRL.pickAudioFile();
    if (!picked) return;
    // Remove existing custom option with same path, then add and select it.
    for (let i = dom.micFileSelect.options.length - 1; i >= 1; i--) {
      if (dom.micFileSelect.options[i].value === picked) {
        dom.micFileSelect.remove(i);
      }
    }
    dom.micFileSelect.add(new Option(picked.split("/").pop(), picked));
    dom.micFileSelect.value = picked;
  } catch (_) {}
});

window.addEventListener("beforeunload", () => { stopReplay(); captionBridge.stop(); savePrefs(); });

// ── Init ──────────────────────────────────────────────────────────────────────

async function init() {
  render();
  setStatus("checking controller…");

  await loadPrefs();
  render();

  // Populate mic device list and audio file list on startup (non-blocking).
  if (typeof CTRL.listMicDevices === "function") refreshMicDevices().catch(() => {});
  if (typeof CTRL.listAudioFiles === "function") loadAudioFiles().catch(() => {});
  updateMicModeVisibility();
  refreshPlaybackDevices().catch(() => {});

  // Wire log streams: split each chunk by line and parse EVENT: lines for transcript.
  if (typeof CTRL.onClientLog === "function") {
    CTRL.onClientLog((chunk) => {
      ingestClientChunk(chunk, "mic");
      // Show non-EVENT lines in debug; show a brief note for EVENT lines.
      const lines = chunk.split("\n").filter(Boolean);
      for (const line of lines) {
        if (line.includes("EVENT:")) {
          appendDebug("[mic] ← segment");
        } else {
          appendDebug("[mic] " + line);
          if ((line.startsWith("client exited") || line.startsWith("client error:")) &&
              state.phase === "running" && !switchingInput && dom.micModeSelect.value === "mic") {
            setStatus("Microphone capture stopped; select a connected device or refresh inputs to retry.", true);
          } else if (line.startsWith("capture warning:")) {
            micCaptureWarning = line;
            setStatus(line, true);
          } else if (line.startsWith("capture recovered:")) {
            micCaptureWarning = null;
            setStatus(line);
          }
        }
      }
    });
  }
  if (typeof CTRL.onDesktopClientLog === "function") {
    CTRL.onDesktopClientLog((chunk) => {
      ingestClientChunk(chunk, "desktop");
      const lines = chunk.split("\n").filter(Boolean);
      for (const line of lines) {
        if (line.includes("EVENT:")) {
          appendDebug("[desktop] ← segment");
        } else {
          appendDebug("[desktop] " + line);
        }
      }
    });
  }
  if (typeof CTRL.onTapSetupLog === "function") {
    CTRL.onTapSetupLog((line) => appendDebug("[tap-setup] " + line.replace(/\n$/, "")));
  }

  startStatusPoll();
}

document.addEventListener("DOMContentLoaded", init);
