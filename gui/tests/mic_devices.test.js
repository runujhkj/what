const assert = require("node:assert/strict");
const { parseDshowAudio, parseAvfoundationAudio, listMicDevices } = require("../lib/mic_devices");

// ffmpeg >= 5 tags each line; microphones are listed, loopback inputs are not.
const dshowTagged = [
  '[in#0 @ 000001] "OBS Virtual Camera" (none)',
  '[in#0 @ 000001] "Microphone (USBAudio2.0)" (audio)',
  '[in#0 @ 000001]   Alternative name "@device_cm_{33D9A762}\wave_{330A}"',
  '[in#0 @ 000001] "Stereo Mix (Realtek(R) Audio)" (audio)',
  '[in#0 @ 000001] "CABLE Output (VB-Audio Virtual Cable)" (audio)',
  "Error opening input file dummy.",
].join("\r\n");
assert.deepEqual(parseDshowAudio(dshowTagged), [{ index: 0, name: "Microphone (USBAudio2.0)" }]);

// Older ffmpeg: section headers instead of tags.
const dshowSections = [
  "[dshow @ 01] DirectShow video devices",
  '[dshow @ 01]  "Integrated Camera"',
  "[dshow @ 01] DirectShow audio devices",
  '[dshow @ 01]  "Headset Microphone (Jabra)"',
  '[dshow @ 01]     Alternative name "@device_cm_{X}"',
].join("\n");
assert.deepEqual(parseDshowAudio(dshowSections), [{ index: 0, name: "Headset Microphone (Jabra)" }]);

const avf = [
  "[AVFoundation indev @ 0x1] AVFoundation video devices:",
  "[AVFoundation indev @ 0x1] [0] FaceTime HD Camera",
  "[AVFoundation indev @ 0x1] AVFoundation audio devices:",
  "[AVFoundation indev @ 0x1] [0] MacBook Pro Microphone",
].join("\n");
assert.deepEqual(parseAvfoundationAudio(avf), [{ index: 0, name: "MacBook Pro Microphone" }]);

const calls = [];
const fakeSpawn = (bin, args) => { calls.push(args); return { stderr: dshowTagged, stdout: "" }; };
assert.equal(listMicDevices({ platform: "win32", spawnSync: fakeSpawn }).length, 1);
assert.ok(calls[0].includes("dshow"));
assert.deepEqual(listMicDevices({ platform: "linux", spawnSync: fakeSpawn }), []);
