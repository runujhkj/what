const assert = require("assert");
const path = require("path");
const rp = require("../lib/runtime_paths");

function testDevPaths() {
  const { pythonRoot, logsDir } = rp.computePaths({
    isPackaged: false, guiDir: "/repo/gui", env: {},
  });
  assert.strictEqual(pythonRoot, path.join("/repo/gui", ".."));
  assert.strictEqual(logsDir, path.join("/repo", "logs"));
}

function testPackagedPaths() {
  const { pythonRoot, logsDir } = rp.computePaths({
    isPackaged: true, resourcesPath: "/app/resources", userDataDir: "/home/u/.config/what", env: {},
  });
  assert.strictEqual(pythonRoot, path.join("/app/resources", "pyruntime"));
  // Read-only resources -> logs under userData.
  assert.strictEqual(logsDir, path.join("/home/u/.config/what", "logs"));
}

function testLogDirEnvOverride() {
  const { logsDir } = rp.computePaths({
    isPackaged: true, resourcesPath: "/app/resources", userDataDir: "/u", env: { WHAT_LOG_DIR: "/custom/logs" },
  });
  assert.strictEqual(logsDir, "/custom/logs");
}

function testResolveCliPrefersEnv() {
  assert.strictEqual(
    rp.resolveWhatCli({ pythonRoot: "/root", env: { WHAT_CLI: "/x/what" }, exists: () => true }),
    "/x/what"
  );
  assert.strictEqual(
    rp.resolveWhatCli({ pythonRoot: "/root", env: { WHAT_PYTHON: "/x/python" }, exists: () => false }),
    "/x/python"
  );
}

function testResolveCliFindsVenvThenFallsBack() {
  const only = path.join("/root", ".venv", "bin", "what");
  assert.strictEqual(
    rp.resolveWhatCli({ pythonRoot: "/root", env: {}, exists: (p) => p === only }),
    only
  );
  assert.strictEqual(
    rp.resolveWhatCli({ pythonRoot: "/root", env: {}, exists: () => false }),
    "what"
  );
}

function testResolvePython() {
  const venvPy = path.join("/root", ".venv", "bin", "python");
  assert.strictEqual(
    rp.resolvePython({ pythonRoot: "/root", env: {}, platform: "linux", exists: (p) => p === venvPy }),
    venvPy
  );
  assert.strictEqual(
    rp.resolvePython({ pythonRoot: "/root", env: { WHAT_PYTHON: "/py" }, exists: () => false }),
    "/py"
  );
  assert.strictEqual(
    rp.resolvePython({ pythonRoot: "/root", env: {}, platform: "linux", exists: () => false }),
    "python3"
  );
}

function testWindowsPrefersPythonw() {
  const venv = path.win32.join("C:", "repo", ".venv", "Scripts");
  const py = path.win32.join(venv, "python.exe");
  const pyw = path.win32.join(venv, "pythonw.exe");
  const has = (p) => p === pyw;
  assert.strictEqual(rp.windowlessPython(py, { platform: "win32", exists: has }), pyw);
  assert.strictEqual(rp.windowlessPython(py, { platform: "win32", exists: () => false }), py);
  assert.strictEqual(rp.windowlessPython("/usr/bin/python", { platform: "linux", exists: () => true }), "/usr/bin/python");
  assert.strictEqual(rp.resolvePython({ pythonRoot: "/r", env: { WHAT_PYTHON: py }, platform: "win32", exists: has }), pyw);
  assert.strictEqual(rp.resolveWhatCli({ pythonRoot: "/r", env: { WHAT_PYTHON: py }, platform: "win32", exists: has }), pyw);
  assert.strictEqual(rp.resolvePython({ pythonRoot: "/r", env: {}, platform: "win32", exists: () => false }), "pythonw");
}

function testBundledPython() {
  const res = path.win32.join("C:", "Program Files", "What", "resources");
  const pyw = path.win32.join(res, "python", "pythonw.exe");
  assert.strictEqual(rp.bundledPython({ resourcesPath: res, platform: "win32", exists: (p) => p === pyw }), pyw);
  assert.strictEqual(rp.bundledPython({ resourcesPath: res, platform: "win32", exists: () => false }), null);
  const posix = path.posix.join("/opt/what/resources", "python", "bin", "python3");
  assert.strictEqual(rp.bundledPython({ resourcesPath: "/opt/what/resources", platform: "linux", exists: (p) => p === posix }), posix);
  assert.strictEqual(rp.bundledPython({ resourcesPath: "", platform: "linux", exists: () => true }), null);
}

testBundledPython();
testWindowsPrefersPythonw();
testDevPaths();
testPackagedPaths();
testLogDirEnvOverride();
testResolveCliPrefersEnv();
testResolveCliFindsVenvThenFallsBack();
testResolvePython();
console.log("runtime_paths.test.js ok");
