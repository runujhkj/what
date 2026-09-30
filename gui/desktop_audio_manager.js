const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const HAL_DIR = "/Library/Audio/Plug-Ins/HAL";
const MANIFEST_REL_PATH = path.join("gui", "desktop_audio_manifest.json");
const RECEIPT_FILE = "desktop-audio-receipt.json";

function isMac() {
  return process.platform === "darwin";
}

function _listHalDrivers() {
  try {
    const names = fs.readdirSync(HAL_DIR);
    return names.filter((name) => name.toLowerCase().endsWith(".driver"));
  } catch (_err) {
    return [];
  }
}

function _isKnownLoopbackDriverName(name) {
  const text = String(name || "").toLowerCase();
  return text.includes("blackhole") || text.includes("loopback") || text.includes("soundflower");
}

function _findInstalledLoopbackDrivers() {
  return _listHalDrivers().filter(_isKnownLoopbackDriverName);
}

function _readJsonFile(filePath) {
  try {
    const raw = fs.readFileSync(filePath, "utf-8");
    const data = JSON.parse(raw);
    return data && typeof data === "object" ? data : null;
  } catch (_err) {
    return null;
  }
}

function _readManifest(repoRoot) {
  const manifestPath = path.join(repoRoot, MANIFEST_REL_PATH);
  const data = _readJsonFile(manifestPath);
  if (!data) return { packages: [] };
  const packages = Array.isArray(data.packages) ? data.packages : [];
  return { packages };
}

function _packageNameForPath(item) {
  const name = String(item && item.name ? item.name : "desktop-audio").trim() || "desktop-audio";
  return `${name}.pkg`;
}

function _sha256File(filePath) {
  const result = spawnSync("shasum", ["-a", "256", filePath], { encoding: "utf-8" });
  if (result.status !== 0) return "";
  const out = String(result.stdout || "").trim();
  return out.split(/\s+/)[0] || "";
}

function _candidatePathsForItem(repoRoot, item) {
  const out = [];
  if (!item || typeof item !== "object") return out;
  const rel = String(item.relative_path || "").trim();
  if (rel) out.push(path.resolve(repoRoot, rel));
  const abs = String(item.absolute_path || "").trim();
  if (abs) out.push(abs);
  const candidates = Array.isArray(item.candidates) ? item.candidates : [];
  for (const entry of candidates) {
    if (!entry || typeof entry !== "object") continue;
    const r = String(entry.relative_path || "").trim();
    if (r) out.push(path.resolve(repoRoot, r));
    const a = String(entry.absolute_path || "").trim();
    if (a) out.push(a);
  }
  return Array.from(new Set(out));
}

function _resolvePkgFromManifest(repoRoot) {
  const manifest = _readManifest(repoRoot);
  const checked_paths = [];
  for (const item of manifest.packages) {
    if (!item || typeof item !== "object") continue;
    const expectedSha = String(item.sha256 || "").trim().toLowerCase();
    const candidates = _candidatePathsForItem(repoRoot, item);
    for (const abs of candidates) {
      checked_paths.push(abs);
      if (!fs.existsSync(abs)) continue;
      if (expectedSha) {
        const actualSha = _sha256File(abs).toLowerCase();
        if (!actualSha || actualSha !== expectedSha) {
          continue;
        }
      }
      return {
        source: "manifest",
        name: String(item.name || "desktop_audio_pkg"),
        pkg_path: abs,
        sha256: expectedSha || "",
        checked_paths,
      };
    }
  }
  return { resolved: null, checked_paths };
}

function _resolveDownloadFromManifest(repoRoot, stateDir) {
  const manifest = _readManifest(repoRoot);
  for (const item of manifest.packages) {
    if (!item || typeof item !== "object") continue;
    const url = String(item.download_url || "").trim();
    if (!url) continue;
    const expectedSha = String(item.sha256 || "").trim().toLowerCase();
    const candidates = _candidatePathsForItem(repoRoot, item);
    const target = candidates[0] || path.join(stateDir, "desktop-audio-cache", _packageNameForPath(item));
    return {
      url,
      sha256: expectedSha,
      target_path: target,
      name: String(item.name || "desktop_audio_pkg"),
    };
  }
  return null;
}

function _resolvePkgFromEnv(checked_paths = []) {
  const envPkg = String(process.env.WHAT_DESKTOP_AUDIO_PKG || "").trim();
  if (!envPkg) return null;
  checked_paths.push(envPkg);
  if (!fs.existsSync(envPkg)) return null;
  return {
    source: "env",
    name: "env_override",
    pkg_path: envPkg,
    sha256: "",
    checked_paths,
  };
}

function _resolvePkg(repoRoot) {
  const manifestResult = _resolvePkgFromManifest(repoRoot);
  const checked = Array.isArray(manifestResult && manifestResult.checked_paths)
    ? manifestResult.checked_paths.slice()
    : [];
  if (manifestResult && manifestResult.pkg_path) {
    return manifestResult;
  }
  const envResolved = _resolvePkgFromEnv(checked);
  if (envResolved) return envResolved;
  return { source: "", name: "", pkg_path: "", sha256: "", checked_paths: checked };
}

function _trimPaths(paths, maxItems = 6) {
  const list = Array.isArray(paths) ? paths.filter(Boolean) : [];
  if (list.length <= maxItems) return list;
  return [...list.slice(0, maxItems - 1), `... (${list.length - (maxItems - 1)} more)`];
}

function _statusBase() {
  return {
    platform: process.platform,
    supported: isMac(),
    installed: false,
    installed_drivers: [],
    managed_install: false,
    managed_drivers: [],
    install_pkg_path: "",
    install_pkg_source: "",
    install_pkg_checked_paths: [],
    download_url: "",
    can_auto_download: false,
    can_auto_install: false,
    can_auto_uninstall: false,
    can_reload_audio: false,
    note: "",
  };
}

function getDesktopAudioManagerStatus(repoRoot, stateDir) {
  const status = _statusBase();
  if (!status.supported) {
    status.note = "Desktop Audio Manager automation is currently macOS-only.";
    return status;
  }
  status.can_reload_audio = true;
  const installed = _findInstalledLoopbackDrivers();
  status.installed_drivers = installed;
  status.installed = installed.length > 0;

  const receipt = _readReceipt(stateDir);
  const receiptDrivers = Array.isArray(receipt && receipt.managed_drivers) ? receipt.managed_drivers : [];
  const managedDrivers = receiptDrivers.filter((name) => installed.includes(name));
  status.managed_drivers = managedDrivers;
  status.managed_install = Boolean(receipt && receipt.installed_by_app && managedDrivers.length > 0);
  status.can_auto_uninstall = status.managed_install;

  const resolved = _resolvePkg(repoRoot);
  const downloadable = _resolveDownloadFromManifest(repoRoot, stateDir);
  status.install_pkg_checked_paths = _trimPaths(resolved.checked_paths);
  if (downloadable && downloadable.url) {
    status.download_url = downloadable.url;
    status.can_auto_download = Boolean(downloadable.sha256);
    if (!downloadable.sha256) {
      status.note = "Desktop audio package download URL is configured but sha256 is missing; auto-download is disabled.";
    }
  }
  if (resolved && resolved.pkg_path) {
    status.install_pkg_path = resolved.pkg_path;
    status.install_pkg_source = resolved.source;
    status.can_auto_install = true;
  } else {
    const checked = status.install_pkg_checked_paths.length
      ? ` Checked: ${status.install_pkg_checked_paths.join(" | ")}`
      : "";
    status.note =
      "No valid desktop audio package found. Add gui/desktop_audio_manifest.json package entry or set WHAT_DESKTOP_AUDIO_PKG." +
      checked;
  }

  if (status.installed && !status.managed_install) {
    status.note = "Loopback driver exists but is unmanaged by this app. Auto-uninstall is disabled for safety.";
  }

  return status;
}

function reloadDesktopAudioDevices(repoRoot, stateDir) {
  const status = getDesktopAudioManagerStatus(repoRoot, stateDir);
  if (!status.supported) {
    return { ok: false, error: "unsupported_platform", status };
  }
  const cmd =
    "launchctl kickstart -k system/com.apple.audio.coreaudiod || " +
    "(killall coreaudiod >/dev/null 2>&1 || true; sleep 1)";
  const result = _runAppleScriptAdmin(cmd);
  if (result.status === 0) {
    return { ok: true, changed: true, status: getDesktopAudioManagerStatus(repoRoot, stateDir) };
  }
  return {
    ok: false,
    error: "reload_failed",
    code: result.status,
    stdout: result.stdout || "",
    stderr: result.stderr || "",
    status: getDesktopAudioManagerStatus(repoRoot, stateDir),
  };
}

function installDesktopAudioComponent(repoRoot, stateDir) {
  const status = getDesktopAudioManagerStatus(repoRoot, stateDir);
  if (!status.supported) {
    return { ok: false, error: "unsupported_platform", status };
  }
  if (status.managed_install) {
    return { ok: true, installed: true, changed: false, status };
  }
  if (status.installed && !status.managed_install) {
    return { ok: false, error: "unmanaged_existing_install", status };
  }
  if (!status.install_pkg_path) {
    return { ok: false, error: "missing_pkg", status };
  }

  const before = _findInstalledLoopbackDrivers();
  const cmd = `installer -pkg '${status.install_pkg_path.replace(/'/g, "'\\''")}' -target /`;
  const result = _runAppleScriptAdmin(cmd);
  const afterDrivers = _findInstalledLoopbackDrivers();
  const newDrivers = afterDrivers.filter((name) => !before.includes(name));
  const managedDrivers = (newDrivers.length > 0 ? newDrivers : afterDrivers).filter(_isKnownLoopbackDriverName);

  if (result.status === 0 && managedDrivers.length > 0) {
    _writeReceipt(stateDir, {
      version: 2,
      installed_by_app: true,
      pkg_path: status.install_pkg_path,
      pkg_source: status.install_pkg_source,
      pkg_checked_paths: status.install_pkg_checked_paths || [],
      managed_drivers: managedDrivers,
      installed_at: new Date().toISOString(),
    });
    return { ok: true, installed: true, changed: true, status: getDesktopAudioManagerStatus(repoRoot, stateDir) };
  }
  return {
    ok: false,
    error: "install_failed",
    code: result.status,
    stdout: result.stdout || "",
    stderr: result.stderr || "",
    status: getDesktopAudioManagerStatus(repoRoot, stateDir),
  };
}

function downloadDesktopAudioComponent(repoRoot, stateDir) {
  const status = getDesktopAudioManagerStatus(repoRoot, stateDir);
  if (!status.supported) {
    return { ok: false, error: "unsupported_platform", status };
  }
  const plan = _resolveDownloadFromManifest(repoRoot, stateDir);
  if (!plan || !plan.url) {
    return { ok: false, error: "missing_download_url", status };
  }
  if (!plan.sha256) {
    return { ok: false, error: "missing_download_sha256", status };
  }

  try {
    fs.mkdirSync(path.dirname(plan.target_path), { recursive: true });
  } catch (_err) {
    // ignore
  }
  const tmpPath = `${plan.target_path}.download`;
  try {
    fs.unlinkSync(tmpPath);
  } catch (_err) {
    // ignore
  }
  const result = spawnSync(
    "curl",
    ["-L", "--fail", "--silent", "--show-error", "-o", tmpPath, plan.url],
    { encoding: "utf-8" }
  );
  if (result.status !== 0 || !fs.existsSync(tmpPath)) {
    return {
      ok: false,
      error: "download_failed",
      code: result.status,
      stdout: result.stdout || "",
      stderr: result.stderr || "",
      status: getDesktopAudioManagerStatus(repoRoot, stateDir),
    };
  }
  const actualSha = _sha256File(tmpPath).toLowerCase();
  if (!actualSha || actualSha !== plan.sha256) {
    try {
      fs.unlinkSync(tmpPath);
    } catch (_err) {
      // ignore
    }
    return {
      ok: false,
      error: "checksum_mismatch",
      expected_sha256: plan.sha256,
      actual_sha256: actualSha || "",
      status: getDesktopAudioManagerStatus(repoRoot, stateDir),
    };
  }
  fs.renameSync(tmpPath, plan.target_path);
  return {
    ok: true,
    downloaded: true,
    pkg_path: plan.target_path,
    status: getDesktopAudioManagerStatus(repoRoot, stateDir),
  };
}

function uninstallDesktopAudioComponent(repoRoot, stateDir) {
  const status = getDesktopAudioManagerStatus(repoRoot, stateDir);
  if (!status.supported) {
    return { ok: false, error: "unsupported_platform", status };
  }
  if (!status.managed_install) {
    return { ok: false, error: "unmanaged_install", status };
  }
  if (!status.managed_drivers.length) {
    _clearReceipt(stateDir);
    return { ok: true, installed: status.installed, changed: false, status: getDesktopAudioManagerStatus(repoRoot, stateDir) };
  }

  const targets = status.managed_drivers
    .filter(_isKnownLoopbackDriverName)
    .map((name) => path.join(HAL_DIR, name))
    .filter((full) => full.startsWith(`${HAL_DIR}/`));
  if (!targets.length) {
    _clearReceipt(stateDir);
    return { ok: true, installed: status.installed, changed: false, status: getDesktopAudioManagerStatus(repoRoot, stateDir) };
  }

  const rmArgs = targets.map((full) => `'${full.replace(/'/g, "'\\''")}'`).join(" ");
  const cmd = `rm -rf ${rmArgs}`;
  const result = _runAppleScriptAdmin(cmd);
  const after = getDesktopAudioManagerStatus(repoRoot, stateDir);
  if (result.status === 0 && !after.managed_install) {
    _clearReceipt(stateDir);
    return { ok: true, installed: after.installed, changed: true, status: getDesktopAudioManagerStatus(repoRoot, stateDir) };
  }
  return {
    ok: false,
    error: "uninstall_failed",
    code: result.status,
    stdout: result.stdout || "",
    stderr: result.stderr || "",
    status: after,
  };
}
function _receiptPath(stateDir) {
  return path.join(stateDir, RECEIPT_FILE);
}

function _readReceipt(stateDir) {
  return _readJsonFile(_receiptPath(stateDir));
}

function _writeReceipt(stateDir, receipt) {
  fs.mkdirSync(stateDir, { recursive: true });
  fs.writeFileSync(_receiptPath(stateDir), JSON.stringify(receipt, null, 2), "utf-8");
}

function _clearReceipt(stateDir) {
  try {
    fs.unlinkSync(_receiptPath(stateDir));
  } catch (_err) {
    // ignore
  }
}

function _runAppleScriptAdmin(command) {
  const script = `do shell script "${command.replace(/"/g, '\\"')}" with administrator privileges`;
  return spawnSync("osascript", ["-e", script], { encoding: "utf-8" });
}


module.exports = {
  downloadDesktopAudioComponent,
  getDesktopAudioManagerStatus,
  installDesktopAudioComponent,
  reloadDesktopAudioDevices,
  uninstallDesktopAudioComponent,
};
