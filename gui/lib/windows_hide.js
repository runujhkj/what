"use strict";

// On Windows, a console program (python, ffmpeg, taskkill) started by Electron -- a GUI
// process with no console -- gets its own visible console window, and closing that window
// kills the process (e.g. the mic client). Default every child_process launch to
// windowsHide so the app's helpers run quietly. Must be applied before any module
// destructures spawn/spawnSync from child_process. An explicit windowsHide wins.

const WRAPPED = ["spawn", "spawnSync", "execFile", "execFileSync", "exec", "execSync", "fork"];

function withHidden(options) {
  if (options && typeof options === "object") {
    return "windowsHide" in options ? options : { ...options, windowsHide: true };
  }
  return { windowsHide: true };
}

// Place the options object wherever this call shape expects it: (cmd, [args], [options], [cb]).
function hideArgs(args) {
  const out = args.slice();
  let i = 1;
  if (Array.isArray(out[i])) i += 1;
  if (typeof out[i] === "function" || out[i] === undefined || out[i] === null) {
    const tail = out.slice(i).filter((v) => v !== undefined && v !== null);
    return [...out.slice(0, i), withHidden(undefined), ...tail];
  }
  out[i] = withHidden(out[i]);
  return out;
}

function hideChildConsoles(childProcess, platform = process.platform) {
  if (platform !== "win32" || childProcess.__whatWindowsHide) return childProcess;
  for (const name of WRAPPED) {
    const original = childProcess[name];
    if (typeof original !== "function") continue;
    childProcess[name] = function hiddenWindow(...args) {
      return original.apply(this, hideArgs(args));
    };
  }
  childProcess.__whatWindowsHide = true;
  return childProcess;
}

module.exports = { hideChildConsoles, hideArgs };
