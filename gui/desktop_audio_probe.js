const { spawn } = require("child_process");

function defaultDesktopBackend() {
  if (process.platform === "darwin") return "avfoundation";
  if (process.platform === "linux") return "pulse";
  if (process.platform === "win32") return "wasapi";
  return "avfoundation";
}

function normalizeDesktopBackend(value) {
  const text = String(value || "").trim().toLowerCase();
  if (!text) return defaultDesktopBackend();
  return text;
}

function parseAvfoundationAudioDevices(output) {
  const devices = [];
  const lines = String(output || "").split(/\r?\n/);
  let inAudio = false;
  for (const line of lines) {
    if (line.includes("AVFoundation audio devices")) {
      inAudio = true;
      continue;
    }
    if (inAudio && line.includes("AVFoundation video devices")) {
      break;
    }
    if (!inAudio) continue;
    const match = line.match(/\[(\d+)\]\s+(.*)$/);
    if (!match) continue;
    devices.push({
      id: match[1],
      label: match[2].trim(),
      value: `:${match[1]}`,
    });
  }
  return devices;
}

function probeAvfoundationDevices(timeoutMs = 7000) {
  return new Promise((resolve) => {
    let stdout = "";
    let stderr = "";
    let settled = false;
    let timedOut = false;

    let child = null;
    try {
      child = spawn("ffmpeg", ["-f", "avfoundation", "-list_devices", "true", "-i", ""], {
        stdio: ["ignore", "pipe", "pipe"],
      });
    } catch (err) {
      resolve({
        ok: false,
        backend: "avfoundation",
        devices: [],
        error: `ffmpeg probe failed: ${String(err && err.message ? err.message : err)}`,
      });
      return;
    }

    const finish = (payload) => {
      if (settled) return;
      settled = true;
      resolve(payload);
    };

    const timer = setTimeout(() => {
      timedOut = true;
      try {
        if (child && child.pid) {
          child.kill("SIGKILL");
        }
      } catch (_err) {
        // ignore
      }
    }, Math.max(500, Number(timeoutMs || 7000)));

    if (child.stdout) {
      child.stdout.on("data", (buf) => {
        stdout += String(buf || "");
      });
    }
    if (child.stderr) {
      child.stderr.on("data", (buf) => {
        stderr += String(buf || "");
      });
    }

    child.on("error", (err) => {
      clearTimeout(timer);
      finish({
        ok: false,
        backend: "avfoundation",
        devices: [],
        error: `ffmpeg probe failed: ${String(err && err.message ? err.message : err)}`,
      });
    });

    child.on("close", (_code) => {
      clearTimeout(timer);
      if (timedOut) {
        finish({
          ok: false,
          backend: "avfoundation",
          devices: [],
          error: "ffmpeg probe timeout",
        });
        return;
      }
      const output = `${stderr || ""}\n${stdout || ""}`;
      finish({
        ok: true,
        backend: "avfoundation",
        devices: parseAvfoundationAudioDevices(output),
      });
    });
  });
}

async function listDesktopDevices(backend) {
  const selected = normalizeDesktopBackend(backend);
  if (selected === "avfoundation") {
    return probeAvfoundationDevices(7000);
  }
  if (selected === "pulse") {
    return {
      ok: true,
      backend: selected,
      devices: [],
      note: "Linux desktop capture probe is stubbed for now.",
    };
  }
  if (selected === "wasapi") {
    return {
      ok: true,
      backend: selected,
      devices: [],
      note: "Windows desktop capture probe is stubbed for now.",
    };
  }
  return {
    ok: false,
    backend: selected,
    devices: [],
    error: `Unsupported desktop backend: ${selected}`,
  };
}

module.exports = {
  defaultDesktopBackend,
  normalizeDesktopBackend,
  listDesktopDevices,
};
