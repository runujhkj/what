"use strict";
const assert = require("node:assert/strict");
const { parseDefaultDevices, readDefaultDevices } = require("../lib/audio_defaults");

// Shape of `system_profiler SPAudioDataType -json` on the owner's Mac (2026-09-18).
const sample = {
  SPAudioDataType: [{
    _name: "coreaudio_device",
    _items: [
      { _name: "DELL U2515H", coreaudio_device_transport: "coreaudio_device_type_hdmi" },
      { _name: "USB Audio Adapter", coreaudio_default_audio_output_device: "spaudio_yes", coreaudio_device_transport: "coreaudio_device_type_usb" },
      { _name: "MacBook Pro Microphone", coreaudio_default_audio_input_device: "spaudio_yes", coreaudio_device_transport: "coreaudio_device_type_builtin" },
      { _name: "MacBook Pro Speakers", coreaudio_default_audio_system_device: "spaudio_yes", coreaudio_device_transport: "coreaudio_device_type_builtin" },
      { _name: "BT Headset", coreaudio_device_transport: "coreaudio_device_type_bluetooth" },
    ],
  }],
};

assert.deepEqual(parseDefaultDevices(sample), {
  output: { name: "USB Audio Adapter", transport: "USB" },
  input: { name: "MacBook Pro Microphone", transport: "built-in" },
  system: { name: "MacBook Pro Speakers", transport: "built-in" },
});
assert.deepEqual(parseDefaultDevices({}), { output: null, input: null, system: null });

(async () => {
  assert.deepEqual(await readDefaultDevices({ platform: "linux" }), { ok: false, error: "unsupported_platform" });
  const ok = await readDefaultDevices({
    platform: "darwin",
    run: (cmd, args, opts, cb) => { assert.equal(cmd, "system_profiler"); cb(null, JSON.stringify(sample)); },
  });
  assert.equal(ok.ok, true);
  assert.equal(ok.output.name, "USB Audio Adapter");
  const bad = await readDefaultDevices({ platform: "darwin", run: (c, a, o, cb) => cb(null, "not json") });
  assert.equal(bad.ok, false);
  const failed = await readDefaultDevices({ platform: "darwin", run: (c, a, o, cb) => cb(new Error("boom")) });
  assert.deepEqual(failed, { ok: false, error: "boom" });
  console.log("audio_defaults tests passed");
})().catch((err) => { console.error(err); process.exit(1); });
