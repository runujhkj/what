"use strict";

// Microphone discovery for the Settings picker, per platform, via ffmpeg's device lists.
// The client resolves the chosen NAME at capture time (see renderer2.js), so only names
// matter here; avfoundation indexes are kept for display compatibility.

// Loopback/virtual-cable inputs are desktop sources, not microphones (mirrors
// what/desktop_audio.py _LOOPBACK_HINTS).
const LOOPBACK_HINTS = ["stereo mix", "what u hear", "wave out mix", "virtual-audio-capturer", "cable output"];

function parseAvfoundationAudio(output) {
  const devices = [];
  let inAudio = false;
  for (const line of String(output || "").split("\n")) {
    if (line.includes("AVFoundation audio devices")) { inAudio = true; continue; }
    if (inAudio && line.includes("AVFoundation video devices")) break;
    if (inAudio) {
      const m = line.match(/\[(\d+)\]\s+(.+)$/);
      if (m) devices.push({ index: Number(m[1]), name: m[2].trim() });
    }
  }
  return devices;
}

// Handles both ffmpeg layouts: a "DirectShow audio devices" section, or "(audio)" tags.
function parseDshowAudio(output) {
  const names = [];
  let inAudio = false;
  for (const line of String(output || "").split(/\r?\n/)) {
    const low = line.toLowerCase();
    if (low.includes("directshow audio devices")) { inAudio = true; continue; }
    if (low.includes("directshow video devices")) { inAudio = false; continue; }
    if (low.includes("alternative name")) continue;
    const m = line.match(/"([^"]+)"/);
    if (m && (inAudio || low.trimEnd().endsWith("(audio)"))) names.push(m[1]);
  }
  const isLoopback = (n) => LOOPBACK_HINTS.some((h) => n.toLowerCase().includes(h));
  return names.filter((n) => !isLoopback(n)).map((name, index) => ({ index, name }));
}

// Returns [{index, name}]; [] where the platform has no picker support (Linux uses the
// PulseAudio default source).
function listMicDevices({ platform = process.platform, spawnSync, ffmpeg = "ffmpeg" }) {
  let args;
  let parse;
  if (platform === "darwin") {
    args = ["-f", "avfoundation", "-list_devices", "true", "-i", ""];
    parse = parseAvfoundationAudio;
  } else if (platform === "win32") {
    args = ["-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"];
    parse = parseDshowAudio;
  } else {
    return [];
  }
  const result = spawnSync(ffmpeg, args, { stdio: "pipe", timeout: 5000, windowsHide: true });
  return parse((result.stderr || "").toString() + (result.stdout || "").toString());
}

module.exports = { parseAvfoundationAudio, parseDshowAudio, listMicDevices };
