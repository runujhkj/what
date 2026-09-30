const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const RECEIPT_FILE = "desktop-audio-routing-receipt.json";

function isMac() {
  return process.platform === "darwin";
}

function _receiptPath(stateDir) {
  return path.join(stateDir, RECEIPT_FILE);
}

function _readJson(filePath) {
  try {
    const raw = fs.readFileSync(filePath, "utf-8");
    const data = JSON.parse(raw);
    return data && typeof data === "object" ? data : null;
  } catch (_err) {
    return null;
  }
}

function _readReceipt(stateDir) {
  return _readJson(_receiptPath(stateDir));
}

function _writeReceipt(stateDir, data) {
  fs.mkdirSync(stateDir, { recursive: true });
  fs.writeFileSync(_receiptPath(stateDir), JSON.stringify(data, null, 2), "utf-8");
}

function _clearReceipt(stateDir) {
  try {
    fs.unlinkSync(_receiptPath(stateDir));
  } catch (_err) {
    // ignore
  }
}

function _findSwitchAudioSource() {
  const candidates = [
    "/opt/homebrew/bin/SwitchAudioSource",
    "/usr/local/bin/SwitchAudioSource",
    "/usr/bin/SwitchAudioSource",
  ];
  for (const full of candidates) {
    if (fs.existsSync(full)) return full;
  }
  const probe = spawnSync("sh", ["-lc", "command -v SwitchAudioSource || true"], { encoding: "utf-8" });
  const found = String(probe.stdout || "").trim();
  if (found) return found;
  return "";
}

function _runSwitch(bin, args) {
  return spawnSync(bin, args, { encoding: "utf-8" });
}

function _listOutputs(bin) {
  const result = _runSwitch(bin, ["-a", "-t", "output"]);
  if (result.status !== 0) return [];
  return String(result.stdout || "")
    .split(/\r?\n/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function _currentOutput(bin) {
  const result = _runSwitch(bin, ["-c", "-t", "output"]);
  if (result.status !== 0) return "";
  return String(result.stdout || "").trim();
}

function _findBlackHoleOutput(outputs) {
  const list = Array.isArray(outputs) ? outputs : [];
  const exact = list.find((name) => /blackhole\s*2ch/i.test(String(name)));
  if (exact) return exact;
  return list.find((name) => /blackhole/i.test(String(name))) || "";
}

function _statusBase() {
  return {
    platform: process.platform,
    supported: isMac(),
    manager: "",
    manager_path: "",
    can_route: false,
    can_restore: false,
    routed: false,
    route_mode: "",
    current_output: "",
    target_output: "",
    note: "",
  };
}

function getAudioRoutingStatus(stateDir) {
  const status = _statusBase();
  if (!status.supported) {
    status.note = "Audio routing automation is currently macOS-only.";
    return status;
  }
  const switchPath = _findSwitchAudioSource();
  if (!switchPath) {
    status.note = "SwitchAudioSource helper not found; auto-routing unavailable.";
    return status;
  }
  status.manager = "switchaudiosource";
  status.manager_path = switchPath;
  status.can_route = true;
  status.current_output = _currentOutput(switchPath);
  const outputs = _listOutputs(switchPath);
  status.target_output = _findBlackHoleOutput(outputs);
  const receipt = _readReceipt(stateDir);
  status.can_restore = Boolean(receipt && receipt.previous_output);
  const cur = String(status.current_output || "").toLowerCase();
  status.routed = Boolean(cur && cur.includes("blackhole"));
  status.route_mode = receipt && receipt.mode ? String(receipt.mode) : "";
  if (!status.target_output) {
    status.note = "BlackHole output device not found yet.";
  }
  return status;
}

function applyDesktopAudioRouting(stateDir) {
  const status = getAudioRoutingStatus(stateDir);
  if (!status.supported) return { ok: false, error: "unsupported_platform", status };
  if (!status.can_route || !status.manager_path) return { ok: false, error: "missing_manager", status };
  if (!status.target_output) return { ok: false, error: "missing_blackhole_output", status };
  const current = String(status.current_output || "");
  if (current && current.toLowerCase().includes("blackhole")) {
    return { ok: true, changed: false, routed: true, status };
  }
  const setResult = _runSwitch(status.manager_path, ["-s", status.target_output, "-t", "output"]);
  if (setResult.status !== 0) {
    return {
      ok: false,
      error: "route_failed",
      code: setResult.status,
      stdout: setResult.stdout || "",
      stderr: setResult.stderr || "",
      status: getAudioRoutingStatus(stateDir),
    };
  }
  const now = getAudioRoutingStatus(stateDir);
  _writeReceipt(stateDir, {
    version: 1,
    mode: "direct_blackhole_output",
    previous_output: current,
    routed_output: status.target_output,
    manager: status.manager,
    manager_path: status.manager_path,
    applied_at: new Date().toISOString(),
  });
  return { ok: true, changed: true, routed: true, status: now };
}

function restoreDesktopAudioRouting(stateDir) {
  const status = getAudioRoutingStatus(stateDir);
  if (!status.supported) return { ok: false, error: "unsupported_platform", status };
  if (!status.manager_path) return { ok: false, error: "missing_manager", status };
  const receipt = _readReceipt(stateDir);
  const previous = String(receipt && receipt.previous_output ? receipt.previous_output : "");
  if (!previous) {
    _clearReceipt(stateDir);
    return { ok: true, changed: false, restored: false, status };
  }
  const setResult = _runSwitch(status.manager_path, ["-s", previous, "-t", "output"]);
  if (setResult.status !== 0) {
    return {
      ok: false,
      error: "restore_failed",
      code: setResult.status,
      stdout: setResult.stdout || "",
      stderr: setResult.stderr || "",
      status: getAudioRoutingStatus(stateDir),
    };
  }
  _clearReceipt(stateDir);
  return { ok: true, changed: true, restored: true, status: getAudioRoutingStatus(stateDir) };
}

module.exports = {
  applyDesktopAudioRouting,
  getAudioRoutingStatus,
  restoreDesktopAudioRouting,
};
