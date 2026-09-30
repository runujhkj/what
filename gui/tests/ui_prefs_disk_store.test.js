const assert = require("assert");
const store = require("../lib/ui_prefs_disk_store");

function testLoadDefaultsAndValidObject() {
  const fsMissing = {
    readFileSync() {
      throw new Error("ENOENT");
    }
  };
  assert.deepStrictEqual(store.loadUiPrefsDisk(fsMissing, "/tmp/ui.json"), {});

  const fsBad = {
    readFileSync() {
      return "not-json";
    }
  };
  assert.deepStrictEqual(store.loadUiPrefsDisk(fsBad, "/tmp/ui.json"), {});

  const fsGood = {
    readFileSync() {
      return JSON.stringify({ inputMode: "desktop", micSourceEnabled: false });
    }
  };
  assert.deepStrictEqual(store.loadUiPrefsDisk(fsGood, "/tmp/ui.json"), {
    inputMode: "desktop",
    micSourceEnabled: false
  });
}

function testSaveSuccessAndErrorShape() {
  const calls = [];
  const fsOk = {
    mkdirSync(dir, opts) {
      calls.push(["mkdirSync", dir, opts]);
    },
    writeFileSync(file, body, enc) {
      calls.push(["writeFileSync", file, body, enc]);
    }
  };
  const pathStub = {
    dirname(v) {
      return `/dir/of/${v}`;
    }
  };
  const ok = store.saveUiPrefsDisk(fsOk, pathStub, "/tmp/ui.json", { inputMode: "mic" });
  assert.deepStrictEqual(ok, { ok: true });
  assert.strictEqual(calls.length, 2);
  assert.strictEqual(calls[1][0], "writeFileSync");

  const fsFail = {
    mkdirSync() {},
    writeFileSync() {
      throw new Error("disk full");
    }
  };
  const fail = store.saveUiPrefsDisk(fsFail, pathStub, "/tmp/ui.json", { a: 1 });
  assert.strictEqual(fail.ok, false);
  assert.ok(String(fail.error || "").includes("disk full"));
}

testLoadDefaultsAndValidObject();
testSaveSuccessAndErrorShape();
console.log("ui_prefs_disk_store.test.js: ok");
