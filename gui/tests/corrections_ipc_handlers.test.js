const assert = require("assert");
const { registerCorrectionsIpcHandlers } = require("../lib/corrections_ipc_handlers");

function makeHarness() {
  const handlers = new Map();
  const ipcMain = {
    handle(name, fn) {
      handlers.set(name, fn);
    }
  };
  const calls = [];
  const fs = {
    mkdirSync(dir, opts) {
      calls.push(["mkdirSync", dir, opts]);
    },
    appendFileSync(file, body) {
      calls.push(["appendFileSync", file, body]);
    },
    writeFileSync(file, body, enc) {
      calls.push(["writeFileSync", file, body, enc]);
    }
  };
  const path = {
    join(...parts) {
      return parts.join("/");
    },
    dirname(file) {
      return file.split("/").slice(0, -1).join("/") || "/";
    }
  };
  const spawnCalls = [];
  const spawnSync = (bin, args, opts) => {
    spawnCalls.push([bin, args, opts]);
    return { status: 0, stdout: JSON.stringify({ ok: true }), stderr: "" };
  };
  return { handlers, ipcMain, fs, path, spawnCalls, spawnSync, calls };
}

async function testRegistrationAndBasicIO() {
  const h = makeHarness();
  registerCorrectionsIpcHandlers({
    ipcMain: h.ipcMain,
    fs: h.fs,
    path: h.path,
    baseDir: "/repo/gui",
    spawnSync: h.spawnSync,
    env: {}
  });

  const names = [
    "append-correction",
    "export-corrections-meta",
    "export-corrections-bundle",
    "import-corrections-bundle",
    "write-obs-output"
  ];
  names.forEach((n) => assert.ok(h.handlers.has(n), `missing ${n}`));

  const appendOut = await h.handlers.get("append-correction")(null, { session_id: "s1", text: "a" });
  assert.strictEqual(appendOut.ok, true);
  assert.ok(String(appendOut.path).includes("/corrections/s1.jsonl"));

  const metaOut = await h.handlers.get("export-corrections-meta")(null, { notes: "n" });
  assert.strictEqual(metaOut.ok, true);
  assert.ok(String(metaOut.path).includes("/corrections/export_meta.json"));

  const writeOut = await h.handlers.get("write-obs-output")(null, { text: "abc" });
  assert.strictEqual(writeOut.ok, true);
  assert.ok(String(writeOut.path).includes("/output/what_obs.txt"));
}

async function testSpawnArgShapeAndErrorMapping() {
  const h = makeHarness();
  const spawnSync = (bin, args, opts) => {
    h.spawnCalls.push([bin, args, opts]);
    if (args.some((arg) => String(arg).includes("export_corrections.py"))) {
      return { status: 0, stdout: JSON.stringify({ ok: true, kind: "exported" }), stderr: "" };
    }
    return { status: 9, stdout: "", stderr: "import boom" };
  };
  registerCorrectionsIpcHandlers({
    ipcMain: h.ipcMain,
    fs: h.fs,
    path: h.path,
    baseDir: "/repo/gui",
    spawnSync,
    env: {}
  });

  const exportOut = await h.handlers.get("export-corrections-bundle")(null, {
    export_dir: "/tmp/export",
    me_speaker_id: "me2",
    instance_id: "i2",
    notes: "hello"
  });
  assert.deepStrictEqual(exportOut, { ok: true, kind: "exported" });
  assert.strictEqual(h.spawnCalls.length, 1);
  assert.ok(h.spawnCalls[0][1].includes("--export-dir"));
  assert.ok(h.spawnCalls[0][1].includes("/tmp/export"));

  const missing = await h.handlers.get("import-corrections-bundle")(null, {});
  assert.strictEqual(missing.ok, false);
  assert.strictEqual(missing.error, "missing bundle_path");

  const importOut = await h.handlers.get("import-corrections-bundle")(null, {
    bundle_path: "/tmp/bundle.jsonl",
    speaker_map: { a: "b" }
  });
  assert.strictEqual(importOut.ok, false);
  assert.ok(String(importOut.error).includes("import boom"));
}

async function run() {
  await testRegistrationAndBasicIO();
  await testSpawnArgShapeAndErrorMapping();
  console.log("corrections_ipc_handlers.test.js: ok");
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
