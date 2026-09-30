const assert = require("assert");
const store = require("../lib/window_state_store");

function testLoadFallbackOnMissingOrMalformed() {
  const fsMissing = {
    readFileSync() {
      throw new Error("ENOENT");
    }
  };
  const fallback = { width: 900, height: 700 };
  const outMissing = store.loadWindowStateFromDisk(fsMissing, "/tmp/missing.json", fallback);
  assert.deepStrictEqual(outMissing, fallback);

  const fsMalformed = {
    readFileSync() {
      return "{not-json";
    }
  };
  const outMalformed = store.loadWindowStateFromDisk(fsMalformed, "/tmp/bad.json", fallback);
  assert.deepStrictEqual(outMalformed, fallback);
}

function testLoadValidAndClamp() {
  const fsGood = {
    readFileSync() {
      return JSON.stringify({ width: 1280, height: 720, x: 50, y: 60 });
    }
  };
  const outGood = store.loadWindowStateFromDisk(fsGood, "/tmp/w.json", { width: 900, height: 700 });
  assert.deepStrictEqual(outGood, { width: 1280, height: 720, x: 50, y: 60 });

  const fsClamp = {
    readFileSync() {
      return JSON.stringify({ width: 100, height: 199, x: "nan", y: 10 });
    }
  };
  const outClamp = store.loadWindowStateFromDisk(fsClamp, "/tmp/w2.json", { width: 900, height: 700 });
  assert.deepStrictEqual(outClamp, { width: 900, height: 700 });
}

function testSaveWritesWhenWindowValid() {
  const calls = [];
  const fsStub = {
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
  const win = {
    isDestroyed() {
      return false;
    },
    getBounds() {
      return { width: 1000, height: 800, x: 10, y: 20 };
    }
  };
  store.saveWindowStateToDisk(fsStub, pathStub, "/tmp/window-state.json", win);
  assert.strictEqual(calls.length, 2);
  assert.strictEqual(calls[0][0], "mkdirSync");
  assert.strictEqual(calls[1][0], "writeFileSync");
  assert.ok(calls[1][2].includes('"width":1000'));
}

function testFitToDisplays() {
  const laptop = [{ x: 0, y: 25, width: 1512, height: 920 }];
  const onScreen = { width: 900, height: 700, x: 100, y: 100 };
  assert.deepStrictEqual(store.fitToDisplays(onScreen, laptop), onScreen);
  // Saved on an external monitor to the right that is no longer connected.
  const offScreen = { width: 900, height: 700, x: 2200, y: 100 };
  assert.deepStrictEqual(store.fitToDisplays(offScreen, laptop), { width: 900, height: 700 });
  // Title bar above the top of the screen.
  assert.deepStrictEqual(store.fitToDisplays({ width: 900, height: 700, x: 100, y: -600 }, laptop),
    { width: 900, height: 700 });
  // Still visible on a second display.
  const two = [...laptop, { x: 1512, y: 0, width: 1920, height: 1080 }];
  assert.deepStrictEqual(store.fitToDisplays(offScreen, two), offScreen);
  // No position saved: unchanged.
  assert.deepStrictEqual(store.fitToDisplays({ width: 900, height: 700 }, laptop), { width: 900, height: 700 });
}

testLoadFallbackOnMissingOrMalformed();
testFitToDisplays();
testLoadValidAndClamp();
testSaveWritesWhenWindowValid();
console.log("window_state_store.test.js: ok");
