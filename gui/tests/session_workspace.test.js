const assert = require("assert");
const path = require("path");
const { createSessionWorkspace } = require("../lib/session_workspace");

(async () => {
  const logsDir = path.join(path.sep, "logs");
  const calls = [];
  const sent = [];
  const timers = [];
  let capturing = false;
  let nextOpen = { canceled: false, filePaths: [path.join(path.sep, "shared", "meeting.what")] };
  let nextSave = { canceled: false, filePath: path.join(path.sep, "shared", "copy") };
  const win = { isDestroyed: () => false, webContents: { send: (ch, p) => sent.push([ch, p]) } };
  const ws = createSessionWorkspace({
    dialog: {
      showOpenDialog: async (_w, opts) => { calls.push(["open-dialog", opts.filters[0].extensions[0]]); return nextOpen; },
      showSaveDialog: async (_w, opts) => { calls.push(["save-dialog", opts.defaultPath]); return nextSave; },
      showMessageBox: async (_w, opts) => { calls.push(["message", opts.message]); },
      showErrorBox: (title, msg) => calls.push(["error", title, msg]),
    },
    shell: { openPath: async (p) => { calls.push(["openPath", p]); return ""; } },
    getArchive: () => ({
      unpack: async (file, dir) => {
        calls.push(["unpack", file, dir]);
        return { ok: true, session_id: "S1", session_dir: path.join(dir, "S1") };
      },
      pack: async (dir, copyTo) => { calls.push(["pack", dir, copyTo || null]); return { ok: true, path: `${dir}/S1.what` }; },
    }),
    loadSessionDir: ({ dir }) => ({ ok: true, sessionId: path.basename(dir), sessionDir: dir, events: [1], corrections: [] }),
    logsDir,
    getWindow: () => win,
    isCapturing: () => capturing,
    fsImpl: { mkdirSync() {} },
    setTimer: (fn) => { timers.push(fn); return timers.length; },
    clearTimer: (id) => { timers[id - 1] = null; },
  });

  // Nothing to save before a session exists.
  assert.equal((await ws.saveSessionAs()).reason, "no_session");

  // Opening while capturing is refused.
  capturing = true;
  assert.equal((await ws.openSession()).reason, "capturing");
  capturing = false;

  // Open: unpack into the logs folder, then send the loaded session to the window.
  assert.deepEqual(await ws.openSession(), { ok: true, sessionId: "S1" });
  assert.deepEqual(calls.find((c) => c[0] === "unpack"), ["unpack", nextOpen.filePaths[0], logsDir]);
  assert.equal(sent.at(-1)[0], "session-loaded");
  assert.equal(sent.at(-1)[1].file, nextOpen.filePaths[0]);
  assert.deepEqual(ws.current, { sessionId: "S1", externalPath: nextOpen.filePaths[0] });

  // Edits are batched, then packed into the logs folder and copied to the opened file.
  ws.correctionSaved("S1");
  ws.correctionSaved("S1");
  assert.equal(timers.filter(Boolean).length, 1);
  await timers.filter(Boolean)[0]();
  timers.fill(null); // that timer has fired
  assert.deepEqual(calls.at(-1), ["pack", path.join(logsDir, "S1"), nextOpen.filePaths[0]]);

  // Save As adds the extension and makes that file the one kept up to date.
  const saved = await ws.saveSessionAs();
  assert.equal(saved.path, `${nextSave.filePath}.what`);
  assert.equal(ws.current.externalPath, `${nextSave.filePath}.what`);

  // Stopping a continued run refreshes the external copy; flush runs it now.
  ws.sessionStopped("S1");
  await ws.flush();
  assert.deepEqual(calls.at(-1), ["pack", path.join(logsDir, "S1"), `${nextSave.filePath}.what`]);

  // A live run reporting a new session drops the external file association.
  ws.setContext("S2");
  assert.deepEqual(ws.current, { sessionId: "S2", externalPath: null });
  ws.sessionStopped("S2");
  assert.equal(timers.filter(Boolean).length, 0);
  ws.setContext("../evil");
  assert.equal(ws.current.sessionId, "S2");

  await ws.showSessionFolder();
  assert.deepEqual(calls.at(-1), ["openPath", path.join(logsDir, "S2")]);

  assert.deepEqual(await ws.newSession(), { ok: true });
  assert.equal(sent.at(-1)[0], "session-new");
  assert.equal(ws.current.sessionId, null);

  // A failed unpack is reported and nothing is sent to the window.
  const failing = createSessionWorkspace({
    dialog: { showOpenDialog: async () => nextOpen, showErrorBox: (t, m) => calls.push(["error", t, m]) },
    shell: {}, logsDir, getWindow: () => win, isCapturing: () => false,
    getArchive: () => ({ unpack: async () => ({ ok: false, error: "not a What session file" }) }),
    loadSessionDir: () => { throw new Error("should not load"); },
  });
  const before = sent.length;
  assert.equal((await failing.openSession()).ok, false);
  assert.deepEqual(calls.at(-1), ["error", "What: could not open session", "not a What session file"]);
  assert.equal(sent.length, before);

  console.log("session_workspace.test.js: ok");
})().catch((err) => { console.error(err); process.exit(1); });
