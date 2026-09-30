const assert = require("node:assert/strict");
const { hideChildConsoles, hideArgs } = require("../lib/windows_hide");

// Options land in the right slot for every call shape.
assert.deepEqual(hideArgs(["py", ["-m", "what"]]), ["py", ["-m", "what"], { windowsHide: true }]);
assert.deepEqual(hideArgs(["py", ["-V"], { cwd: "/x" }]), ["py", ["-V"], { cwd: "/x", windowsHide: true }]);
assert.deepEqual(hideArgs(["py", { env: {} }]), ["py", { env: {}, windowsHide: true }]);
const cb = () => {};
assert.deepEqual(hideArgs(["py", ["-V"], cb]), ["py", ["-V"], { windowsHide: true }, cb]);
assert.deepEqual(hideArgs(["py", ["-V"], { windowsHide: false }]), ["py", ["-V"], { windowsHide: false }]);

// Patches only on Windows, and only once.
const calls = [];
const fake = () => ({ spawn: (...a) => calls.push(a), spawnSync: (...a) => calls.push(a) });
const linux = hideChildConsoles(fake(), "linux");
linux.spawn("ffmpeg", ["-i"]);
assert.deepEqual(calls.pop(), ["ffmpeg", ["-i"]]);
const win = hideChildConsoles(fake(), "win32");
hideChildConsoles(win, "win32");
win.spawnSync("taskkill", ["/T"], { stdio: "ignore" });
assert.deepEqual(calls.pop(), ["taskkill", ["/T"], { stdio: "ignore", windowsHide: true }]);
