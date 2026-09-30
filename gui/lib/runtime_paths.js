"use strict";

// Resolve where the Python side of the app lives, and where logs go, in both a source
// checkout (dev) and a packaged app (electron-builder AppImage).
//
// Dev: gui/ sits one level under the repo root, which holds the `what` package, config/,
// and the .venv/_venv virtualenv. Packaged: the Python tree is bundled read-only under
// resources/pyruntime via electron-builder `extraResources`, and logs must go to a
// writable per-user location instead.
//
// Pure and dependency-injected so it unit-tests without electron: callers pass isPackaged,
// resourcesPath, userDataDir and guiDir; main.js supplies them from the electron `app`.

const path = require("path");
const fs = require("fs");

function computePaths(opts = {}) {
  const {
    isPackaged = false,
    resourcesPath = "",
    userDataDir = "",
    guiDir = __dirname,
    env = process.env,
  } = opts;

  const pythonRoot = isPackaged
    ? path.join(resourcesPath, "pyruntime")
    : path.join(guiDir, "..");

  let logsDir;
  if (env.WHAT_LOG_DIR) {
    logsDir = env.WHAT_LOG_DIR;
  } else if (isPackaged) {
    // resources/ is read-only in an AppImage; keep recordings under userData.
    logsDir = path.join(userDataDir, "logs");
  } else {
    logsDir = path.join(pythonRoot, "logs");
  }

  return { pythonRoot, logsDir };
}

// On Windows prefer pythonw.exe beside python.exe. A venv's python.exe is a launcher that
// starts the real interpreter as a new console process, so even a hidden launch pops up a
// console window (closing it kills capture). pythonw never gets a console and still uses
// the stdio pipes it is given.
function windowlessPython(py, opts = {}) {
  const { platform = process.platform, exists = fs.existsSync } = opts;
  if (platform !== "win32" || !py) return py;
  const pathApi = platform === "win32" ? path.win32 : path;
  if (!/^python(\.exe)?$/i.test(pathApi.basename(py))) return py;
  const candidate = pathApi.join(pathApi.dirname(py), "pythonw.exe");
  return exists(candidate) ? candidate : py;
}

// The `what` CLI entry point (console script). Env overrides win so a developer can point
// at any interpreter. Order preserves the historical _venv (macOS) before .venv (Linux).
function resolveWhatCli(opts = {}) {
  const { pythonRoot, env = process.env, exists = fs.existsSync, platform = process.platform } = opts;
  if (env.WHAT_CLI) return env.WHAT_CLI;
  if (env.WHAT_PYTHON) return windowlessPython(env.WHAT_PYTHON, { platform, exists });
  for (const dir of ["_venv", ".venv"]) {
    const cli = path.join(pythonRoot, dir, "bin", "what");
    if (exists(cli)) return cli;
  }
  return "what";
}

// The Python interpreter to run `-m what` with (Linux desktop capture and the packaged
// path invoke the module rather than the console script).
function resolvePython(opts = {}) {
  const { pythonRoot, env = process.env, exists = fs.existsSync, platform = process.platform } = opts;
  if (env.WHAT_PYTHON) return windowlessPython(env.WHAT_PYTHON, { platform, exists });
  const rel = platform === "win32" ? ["Scripts", "pythonw.exe"] : ["bin", "python"];
  for (const dir of [".venv", "_venv"]) {
    const py = path.join(pythonRoot, dir, ...rel);
    if (exists(py)) return py;
  }
  return platform === "win32" ? "pythonw" : "python3";
}

// A packaged build may bundle a relocatable Python with the app's dependencies already
// installed (the Windows installer does; see scripts/package/build_windows.ps1) under
// resources/python. Returns its interpreter, or null to fall back to first-run venv setup.
function bundledPython(opts = {}) {
  const { resourcesPath = "", platform = process.platform, exists = fs.existsSync } = opts;
  if (!resourcesPath) return null;
  const pathApi = platform === "win32" ? path.win32 : path.posix;
  const py = platform === "win32"
    ? pathApi.join(resourcesPath, "python", "pythonw.exe")
    : pathApi.join(resourcesPath, "python", "bin", "python3");
  return exists(py) ? py : null;
}

module.exports = { computePaths, resolveWhatCli, resolvePython, windowlessPython, bundledPython };
