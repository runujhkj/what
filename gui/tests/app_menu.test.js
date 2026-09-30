const assert = require("assert");
const { buildMenuTemplate } = require("../lib/app_menu");

(async () => {
  const called = [];
  const errors = [];
  const actions = {
    openSession: () => called.push("open"),
    saveSessionAs: () => called.push("save"),
    showSessionFolder: () => { throw new Error("boom"); },
    newSession: () => called.push("new"),
  };
  for (const platform of ["darwin", "win32", "linux"]) {
    const menu = buildMenuTemplate({ platform, appName: "What", actions, onError: (e) => errors.push(e.message) });
    const file = menu.find((m) => m.label === "File");
    const labels = file.submenu.filter((i) => i.label).map((i) => i.label);
    assert.deepEqual(labels, ["Open Session…", "Save Session As…", "Show Session Folder", "New Session"], platform);
    assert.equal(file.submenu[0].accelerator, "CmdOrCtrl+O");
    // Edit roles keep copy/paste/undo working while editing transcript text.
    assert.ok(menu.some((m) => m.role === "editMenu"), platform);
    assert.equal(menu[0].role === "appMenu", platform === "darwin");
    assert.equal(file.submenu.at(-1).role, platform === "darwin" ? "close" : "quit");
    for (const item of file.submenu.filter((i) => i.click)) await item.click();
  }
  assert.deepEqual(called, Array(3).fill(["open", "save", "new"]).flat());
  assert.deepEqual(errors, ["boom", "boom", "boom"]);
  console.log("app_menu.test.js: ok");
})().catch((err) => { console.error(err); process.exit(1); });
