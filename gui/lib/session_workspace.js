"use strict";

// The File menu's session commands, kept out of main.js so they can be tested with fakes.
//
// A session lives in <logsDir>/<session_id>/. Its .what file (what/session_files.py) is
// written there when a run stops and refreshed here after review edits. When a session was
// opened from, or saved to, a .what file somewhere else, that file is kept up to date too,
// the way a document is.

const path = require("path");
const { isSafeId } = require("./review_audio");

const FILTERS = [{ name: "What session", extensions: ["what"] }];
const REPACK_DELAY_MS = 2000;

function createSessionWorkspace({
  dialog,
  shell,
  getArchive,
  loadSessionDir,
  logsDir,
  getWindow,
  isCapturing,
  fsImpl = require("fs"),
  setTimer = setTimeout,
  clearTimer = clearTimeout,
}) {
  // The session the window is showing, and the .what file outside the logs folder that
  // should follow its edits (null when there is none).
  let current = { sessionId: null, externalPath: null };
  const pendingRepacks = new Map(); // sessionId -> timer

  const sessionDir = (sessionId) => path.join(logsDir, sessionId);
  const send = (channel, payload) => {
    const win = getWindow();
    if (win && !win.isDestroyed()) win.webContents.send(channel, payload);
  };
  const tell = (message) => dialog.showMessageBox(getWindow() || undefined, { type: "info", message });
  const fail = (title, error) => dialog.showErrorBox(title, String(error || "unknown error"));

  function isInside(file, dir) {
    const rel = path.relative(dir, file);
    return !!rel && !rel.startsWith("..") && !path.isAbsolute(rel);
  }

  async function openSession() {
    if (isCapturing()) {
      await tell("Stop the running session before opening another.");
      return { ok: false, reason: "capturing" };
    }
    const picked = await dialog.showOpenDialog(getWindow() || undefined, {
      title: "Open Session", properties: ["openFile"], filters: FILTERS,
    });
    if (picked.canceled || !picked.filePaths || !picked.filePaths.length) return { ok: false, reason: "canceled" };
    return openSessionFile(picked.filePaths[0]);
  }

  async function openSessionFile(file) {
    const unpacked = await getArchive().unpack(file, logsDir);
    if (!unpacked.ok) {
      fail("What: could not open session", unpacked.error);
      return unpacked;
    }
    const loaded = loadSessionDir({ dir: unpacked.session_dir, fsImpl });
    if (!loaded.ok) {
      fail("What: could not open session", loaded.error);
      return loaded;
    }
    current = {
      sessionId: loaded.sessionId,
      externalPath: isInside(file, loaded.sessionDir) ? null : file,
    };
    send("session-loaded", { ...loaded, file });
    return { ok: true, sessionId: loaded.sessionId };
  }

  async function saveSessionAs() {
    if (!current.sessionId) {
      await tell("There is no session to save yet. Start one, or open a session file.");
      return { ok: false, reason: "no_session" };
    }
    const picked = await dialog.showSaveDialog(getWindow() || undefined, {
      title: "Save Session As",
      defaultPath: current.externalPath || `${current.sessionId}.what`,
      filters: FILTERS,
    });
    if (picked.canceled || !picked.filePath) return { ok: false, reason: "canceled" };
    const target = picked.filePath.endsWith(".what") ? picked.filePath : `${picked.filePath}.what`;
    const result = await getArchive().pack(sessionDir(current.sessionId), target);
    if (!result.ok) {
      fail("What: could not save session", result.error);
      return result;
    }
    current = { ...current, externalPath: target };
    return { ok: true, path: target };
  }

  async function showSessionFolder() {
    const dir = current.sessionId ? sessionDir(current.sessionId) : logsDir;
    try { fsImpl.mkdirSync(dir, { recursive: true }); } catch (_) {}
    const error = await shell.openPath(dir);
    if (error) fail("What: could not open folder", error);
  }

  async function newSession() {
    if (isCapturing()) {
      await tell("Stop the running session first.");
      return { ok: false, reason: "capturing" };
    }
    current = { sessionId: null, externalPath: null };
    send("session-new", {});
    return { ok: true };
  }

  // The window reports the session it is showing (a live run learns its id from events).
  function setContext(sessionId) {
    if (!sessionId) {
      current = { sessionId: null, externalPath: null };
    } else if (isSafeId(sessionId) && sessionId !== current.sessionId) {
      current = { sessionId, externalPath: null };
    }
    return { ok: true };
  }

  function repack(sessionId) {
    pendingRepacks.delete(sessionId);
    const copyTo = sessionId === current.sessionId ? current.externalPath : null;
    return getArchive().pack(sessionDir(sessionId), copyTo);
  }

  // After a review edit is saved, refresh transcript.txt and the .what file(s), batched.
  function correctionSaved(sessionId) {
    if (!isSafeId(sessionId)) return;
    const pending = pendingRepacks.get(sessionId);
    if (pending) clearTimer(pending);
    pendingRepacks.set(sessionId, setTimer(() => { repack(sessionId); }, REPACK_DELAY_MS));
  }

  // A run of the current session ended. The controller has refreshed the copy in the logs
  // folder; a .what file outside it (opened from, or saved to) needs the new recordings too.
  function sessionStopped(sessionId) {
    if (sessionId && sessionId === current.sessionId && current.externalPath) correctionSaved(sessionId);
    return { ok: true };
  }

  // Run any batched refresh now (on quit).
  function flush() {
    const ids = [...pendingRepacks.keys()];
    for (const id of ids) clearTimer(pendingRepacks.get(id));
    return Promise.all(ids.map(repack));
  }

  return {
    openSession,
    openSessionFile,
    saveSessionAs,
    showSessionFolder,
    newSession,
    setContext,
    correctionSaved,
    sessionStopped,
    flush,
    get current() { return { ...current }; },
  };
}

module.exports = { createSessionWorkspace, REPACK_DELAY_MS };
