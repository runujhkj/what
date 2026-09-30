const assert = require("assert");
const { EventEmitter } = require("events");
const { createSessionArchive } = require("../lib/session_archive");

(async () => {
  const runs = [];
  const fakeSpawn = (stdout, code = 0, stderr = "") => (cmd, args, opts) => {
    runs.push([cmd, args, opts.cwd]);
    const proc = new EventEmitter();
    proc.stdout = new EventEmitter();
    proc.stderr = new EventEmitter();
    setImmediate(() => {
      if (stdout) proc.stdout.emit("data", stdout);
      if (stderr) proc.stderr.emit("data", stderr);
      proc.emit("close", code);
    });
    return proc;
  };

  const ok = createSessionArchive({ spawn: fakeSpawn('{"ok": true, "session_id": "S1", "session_dir": "/logs/S1"}\n'),
    python: "py", cwd: "/root" });
  assert.deepEqual(await ok.unpack("/tmp/a.what", "/logs"), { ok: true, session_id: "S1", session_dir: "/logs/S1" });
  assert.deepEqual(runs.at(-1), ["py", ["-m", "what", "session", "unpack", "/tmp/a.what", "--logs-dir", "/logs", "--json"], "/root"]);

  await createSessionArchive({ spawn: fakeSpawn('{"ok": true, "path": "x"}'), python: "py", cwd: "/root" })
    .pack("/logs/S1", "/out/S1.what");
  assert.deepEqual(runs.at(-1)[1], ["-m", "what", "session", "pack", "/logs/S1", "--copy-to", "/out/S1.what", "--json"]);

  // An error JSON line is passed through; a crash becomes { ok: false } with stderr detail.
  const refused = createSessionArchive({ spawn: fakeSpawn('{"ok": false, "error": "different session"}', 1), python: "py", cwd: "/" });
  assert.deepEqual(await refused.unpack("a", "b"), { ok: false, error: "different session" });
  const crashed = createSessionArchive({ spawn: fakeSpawn("", 1, "Traceback...\nModuleNotFoundError: No module named 'what'\n"), python: "py", cwd: "/" });
  const result = await crashed.pack("/logs/S1");
  assert.equal(result.ok, false);
  assert.match(result.error, /exit 1.*No module named 'what'/s);
  const missing = createSessionArchive({ spawn: () => { throw new Error("ENOENT"); }, python: "py", cwd: "/" });
  assert.match((await missing.pack("/x")).error, /could not start Python: ENOENT/);

  console.log("session_archive.test.js: ok");
})().catch((err) => { console.error(err); process.exit(1); });
