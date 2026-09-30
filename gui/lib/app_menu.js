"use strict";

// The application menu. Electron's default menu is replaced so File can offer session
// files; the Edit, View and Window menus keep Electron's standard roles (Edit's roles are
// what make copy/paste and undo work while editing a transcript segment on macOS).

function buildMenuTemplate({ platform = process.platform, appName = "What", actions, onError = console.error }) {
  const isMac = platform === "darwin";
  // Menu clicks have no caller to report to, so a failed action is logged, not dropped.
  const run = (name) => () => Promise.resolve().then(() => actions[name]()).catch(onError);
  const file = {
    label: "File",
    submenu: [
      { label: "Open Session…", accelerator: "CmdOrCtrl+O", click: run("openSession") },
      { label: "Save Session As…", accelerator: "CmdOrCtrl+Shift+S", click: run("saveSessionAs") },
      { label: "Show Session Folder", click: run("showSessionFolder") },
      { type: "separator" },
      { label: "New Session", accelerator: "CmdOrCtrl+N", click: run("newSession") },
      { type: "separator" },
      isMac ? { role: "close" } : { role: "quit" },
    ],
  };
  return [
    ...(isMac ? [{ label: appName, role: "appMenu" }] : []),
    file,
    { role: "editMenu" },
    { role: "viewMenu" },
    { role: "windowMenu" },
  ];
}

module.exports = { buildMenuTemplate };
