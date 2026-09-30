"use strict";

// First-run Python provisioning for the packaged app.
//
// The AppImage ships the `what` source read-only under resources/pyruntime but no venv (see
// docs/packaging_linux.md). On first launch the app creates a virtualenv in the user's data
// dir and installs only the third-party DEPENDENCIES into it; the `what` package itself is
// imported from the read-only bundled source (`python -m what` runs with cwd = pyruntime,
// which also holds config/). This deliberately avoids installing the package: an editable
// install would write into the read-only source, and a wheel build would need LICENSE/README
// that the staged tree omits. In a source checkout none of this runs -- the developer's .venv
// is used as before.
//
// The path/decision logic is pure and injectable so it unit-tests without spawning anything;
// ensureVenv() performs the actual venv creation and pip install.

const path = require("path");
const fs = require("fs");

// Mirror of pyproject.toml [project.optional-dependencies] service + client (their union),
// plus setuptools: Python 3.12 venvs omit it, and webrtcvad imports pkg_resources from it.
// Keep in sync with pyproject.toml.
const DEPENDENCIES = [
  "setuptools<81",
  "fastapi",
  // Apple Silicon transcribes with the WhisperKit worker (what/asr.py resolve_engine_name);
  // faster-whisper and its native libraries would only slow Gatekeeper's first-launch scan.
  "faster-whisper; sys_platform != 'darwin'",
  "numpy",
  "soundcard; sys_platform == 'win32'",
  "uvicorn",
  "webrtcvad-wheels",
  "websockets",
  "zeroconf",
];

function venvDir(userDataDir) {
  return path.join(userDataDir, "pyvenv");
}

function venvPython(userDataDir) {
  return path.join(venvDir(userDataDir), "bin", "python");
}

// Written only after a successful dependency install. Gating on this (not just the venv
// interpreter's existence) means a venv left half-built by a failed first install -- python
// present but no deps -- is repaired on the next launch instead of being treated as done.
function provisionedMarker(userDataDir) {
  return path.join(venvDir(userDataDir), ".what-provisioned");
}

// True until dependencies have been fully installed at least once.
function needsProvision(userDataDir, exists = fs.existsSync) {
  return !exists(provisionedMarker(userDataDir));
}

// Ensure a usable venv exists, creating and populating it on first run. `run` is a function
// (cmd, args, opts) -> { status } used to invoke python/pip; injected for testing. Returns
// the venv interpreter path. Throws with an actionable message if a step fails.
function ensureVenv(opts) {
  const {
    userDataDir,
    basePython = "python3",
    run,
    exists = fs.existsSync,
    writeMarker = (p) => fs.writeFileSync(p, new Date().toISOString() + "\n"),
    log = () => {},
  } = opts;

  const py = venvPython(userDataDir);
  if (exists(provisionedMarker(userDataDir))) return py;

  log("provisioning python runtime (first run); this downloads dependencies and can take a while...\n");
  // Create the venv only if its interpreter is missing; a half-built venv from a failed
  // earlier attempt keeps its interpreter, so we skip straight to (re)installing deps.
  if (!exists(py)) {
    const created = run(basePython, ["-m", "venv", venvDir(userDataDir)], {});
    if (!created || created.status !== 0) {
      throw new Error(`could not create virtualenv with ${basePython} (Python 3.12 required on PATH)`);
    }
  }

  // Install the third-party dependencies only; `what` is imported from the bundled source.
  const installed = run(py, ["-m", "pip", "install", ...DEPENDENCIES], {});
  if (!installed || installed.status !== 0) {
    throw new Error("dependency install failed (see details below)");
  }
  writeMarker(provisionedMarker(userDataDir));
  log("python runtime ready\n");
  return py;
}

module.exports = { venvDir, venvPython, provisionedMarker, needsProvision, ensureVenv, DEPENDENCIES };
