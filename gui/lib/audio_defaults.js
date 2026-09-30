const { execFile } = require("child_process");

// Snapshot of the macOS default audio devices, used to detect (and attribute) a change of
// the output device while a session starts. Opening a Bluetooth headset microphone, for
// example, switches the headset to its call profile and macOS may move system output.
// system_profiler is used because it needs no extra tools and answers in ~0.3 s.

const TRANSPORTS = {
  coreaudio_device_type_bluetooth: "Bluetooth",
  coreaudio_device_type_usb: "USB",
  coreaudio_device_type_builtin: "built-in",
  coreaudio_device_type_hdmi: "HDMI",
  coreaudio_device_type_displayport: "DisplayPort",
  coreaudio_device_type_virtual: "virtual",
  coreaudio_device_type_aggregate: "aggregate",
  coreaudio_device_type_airplay: "AirPlay",
};

function transportLabel(raw) {
  const key = String(raw || "");
  if (TRANSPORTS[key]) return TRANSPORTS[key];
  return key.replace(/^coreaudio_device_type_/, "") || "unknown";
}

function parseDefaultDevices(json) {
  const items = (((json || {}).SPAudioDataType || [])[0] || {})._items || [];
  const pick = (flag) => {
    const dev = items.find((d) => d && d[flag] === "spaudio_yes");
    return dev ? { name: String(dev._name || ""), transport: transportLabel(dev.coreaudio_device_transport) } : null;
  };
  return {
    output: pick("coreaudio_default_audio_output_device"),
    input: pick("coreaudio_default_audio_input_device"),
    system: pick("coreaudio_default_audio_system_device"),
  };
}

function readDefaultDevices({ platform = process.platform, run = execFile } = {}) {
  if (platform !== "darwin") return Promise.resolve({ ok: false, error: "unsupported_platform" });
  return new Promise((resolve) => {
    run("system_profiler", ["SPAudioDataType", "-json"], { timeout: 5000, maxBuffer: 4 * 1024 * 1024 }, (err, stdout) => {
      if (err) { resolve({ ok: false, error: String(err.message || err) }); return; }
      try {
        resolve({ ok: true, ...parseDefaultDevices(JSON.parse(String(stdout))) });
      } catch (parseErr) {
        resolve({ ok: false, error: `unparseable system_profiler output: ${parseErr.message}` });
      }
    });
  });
}

module.exports = { parseDefaultDevices, readDefaultDevices, transportLabel };
