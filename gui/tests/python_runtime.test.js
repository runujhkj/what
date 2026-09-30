const assert = require("assert");
const path = require("path");
const pr = require("../lib/python_runtime");

function testVenvPaths() {
  assert.strictEqual(pr.venvDir("/u"), path.join("/u", "pyvenv"));
  assert.strictEqual(pr.venvPython("/u"), path.join("/u", "pyvenv", "bin", "python"));
}

function testNeedsProvision() {
  assert.strictEqual(pr.needsProvision("/u", () => false), true);
  const marker = pr.provisionedMarker("/u");
  // Gated on the success marker, not the interpreter: a half-built venv still needs work.
  assert.strictEqual(pr.needsProvision("/u", (p) => p === pr.venvPython("/u")), true);
  assert.strictEqual(pr.needsProvision("/u", (p) => p === marker), false);
}

function testDependenciesMirrorPyproject() {
  // Deps-only install (not the `what` package). setuptools guards webrtcvad's pkg_resources.
  assert.ok(pr.DEPENDENCIES.some((d) => d.startsWith("faster-whisper")));
  assert.ok(pr.DEPENDENCIES.includes("webrtcvad-wheels"));
  assert.ok(pr.DEPENDENCIES.some((d) => d.startsWith("setuptools")));
  assert.ok(!pr.DEPENDENCIES.some((d) => d.startsWith("-e") || d.includes("[")));
}

function testEnsureVenvSkipsWhenMarkerPresent() {
  const marker = pr.provisionedMarker("/u");
  const calls = [];
  const out = pr.ensureVenv({
    userDataDir: "/u",
    run: (...a) => { calls.push(a); return { status: 0 }; },
    exists: (p) => p === marker,
    writeMarker: () => {},
  });
  assert.strictEqual(out, pr.venvPython("/u"));
  assert.strictEqual(calls.length, 0); // already provisioned -> no work
}

function testEnsureVenvCreatesAndInstallsDepsOnly() {
  const calls = [];
  let markerWritten = null;
  const out = pr.ensureVenv({
    userDataDir: "/u", basePython: "python3",
    run: (cmd, args) => { calls.push([cmd, args]); return { status: 0 }; },
    exists: () => false, // nothing present yet
    writeMarker: (p) => { markerWritten = p; },
  });
  assert.strictEqual(out, pr.venvPython("/u"));
  assert.deepStrictEqual(calls[0], ["python3", ["-m", "venv", pr.venvDir("/u")]]);
  assert.deepStrictEqual(calls[1], [pr.venvPython("/u"), ["-m", "pip", "install", ...pr.DEPENDENCIES]]);
  assert.strictEqual(markerWritten, pr.provisionedMarker("/u")); // marker written on success
}

function testEnsureVenvRepairsHalfBuiltVenv() {
  // Interpreter exists but no marker (failed earlier install): reinstall deps, don't re-venv.
  const py = pr.venvPython("/u");
  const calls = [];
  pr.ensureVenv({
    userDataDir: "/u",
    run: (cmd, args) => { calls.push([cmd, args]); return { status: 0 }; },
    exists: (p) => p === py, // python present, marker absent
    writeMarker: () => {},
  });
  assert.strictEqual(calls.length, 1); // no venv creation
  assert.deepStrictEqual(calls[0], [py, ["-m", "pip", "install", ...pr.DEPENDENCIES]]);
}

function testEnsureVenvThrowsOnVenvFailure() {
  let threw = false;
  try {
    pr.ensureVenv({
      userDataDir: "/u",
      run: () => ({ status: 1 }),
      exists: () => false,
    });
  } catch (e) {
    threw = /virtualenv/.test(e.message);
  }
  assert.ok(threw, "expected venv creation failure to throw");
}

function testEnsureVenvThrowsOnInstallFailure() {
  let threw = false;
  try {
    pr.ensureVenv({
      userDataDir: "/u",
      run: (cmd, args) => ({ status: args.includes("venv") ? 0 : 1 }), // venv ok, pip fails
      exists: () => false,
    });
  } catch (e) {
    threw = /install failed/.test(e.message);
  }
  assert.ok(threw, "expected dependency install failure to throw");
}

testVenvPaths();
testNeedsProvision();
testDependenciesMirrorPyproject();
testEnsureVenvSkipsWhenMarkerPresent();
testEnsureVenvCreatesAndInstallsDepsOnly();
testEnsureVenvRepairsHalfBuiltVenv();
testEnsureVenvThrowsOnVenvFailure();
testEnsureVenvThrowsOnInstallFailure();
console.log("python_runtime.test.js ok");
