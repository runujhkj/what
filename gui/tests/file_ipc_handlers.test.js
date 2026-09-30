const assert = require("assert");
const { registerFileIpcHandlers } = require("../lib/file_ipc_handlers");

function makeHarness() {
  const handlers = new Map();
  const ipcMain = {
    handle(name, fn) {
      handlers.set(name, fn);
    }
  };
  const openResults = [];
  const saveResults = [];
  const dialog = {
    showOpenDialog(opts) {
      if (opts && opts.title && opts.title.includes("corrections")) {
        return Promise.resolve(openResults[1]);
      }
      return Promise.resolve(openResults[0]);
    },
    showSaveDialog() {
      return Promise.resolve(saveResults[0]);
    }
  };
  const fs = {
    readdirSync() {
      return ["a.wav", "b.txt", "C.WAV"];
    }
  };
  const path = {
    join(...parts) {
      return parts.join("/");
    }
  };
  return { handlers, ipcMain, dialog, fs, path, openResults, saveResults };
}

async function testRegistrationAndReturnShapes() {
  const h = makeHarness();
  h.openResults.push({ canceled: false, filePaths: ["/tmp/audio.wav"] });
  h.openResults.push({ canceled: false, filePaths: ["/tmp/bundle.jsonl"] });
  h.saveResults.push({ canceled: false, filePath: "/tmp/out.txt" });

  registerFileIpcHandlers({
    ipcMain: h.ipcMain,
    dialog: h.dialog,
    fs: h.fs,
    path: h.path,
    baseDir: "/repo/gui"
  });

  ["pick-audio-file", "pick-corrections-bundle", "pick-obs-output", "list-audio-files"].forEach((name) => {
    assert.ok(h.handlers.has(name), `missing handler ${name}`);
  });

  const audio = await h.handlers.get("pick-audio-file")();
  const bundle = await h.handlers.get("pick-corrections-bundle")();
  const out = await h.handlers.get("pick-obs-output")();
  const files = await h.handlers.get("list-audio-files")();

  assert.strictEqual(audio, "/tmp/audio.wav");
  assert.strictEqual(bundle, "/tmp/bundle.jsonl");
  assert.strictEqual(out, "/tmp/out.txt");
  assert.deepStrictEqual(files, [
    { path: "/repo/gui/../audio/a.wav", label: "audio/a.wav" },
    { path: "/repo/gui/../audio/C.WAV", label: "audio/C.WAV" }
  ]);
}

async function testCancelAndReadErrorPaths() {
  const h = makeHarness();
  h.openResults.push({ canceled: true, filePaths: [] });
  h.openResults.push({ canceled: true, filePaths: [] });
  h.saveResults.push({ canceled: true });
  h.fs.readdirSync = function () {
    throw new Error("ENOENT");
  };

  registerFileIpcHandlers({
    ipcMain: h.ipcMain,
    dialog: h.dialog,
    fs: h.fs,
    path: h.path,
    baseDir: "/repo/gui"
  });

  assert.strictEqual(await h.handlers.get("pick-audio-file")(), null);
  assert.strictEqual(await h.handlers.get("pick-corrections-bundle")(), null);
  assert.strictEqual(await h.handlers.get("pick-obs-output")(), null);
  assert.deepStrictEqual(await h.handlers.get("list-audio-files")(), []);
}

async function run() {
  await testRegistrationAndReturnShapes();
  await testCancelAndReadErrorPaths();
  console.log("file_ipc_handlers.test.js: ok");
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
