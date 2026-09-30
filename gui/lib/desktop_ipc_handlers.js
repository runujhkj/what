function registerDesktopIpcHandlers({
  ipcMain,
  app,
  path,
  baseDir,
  desktopAudioProbe,
  desktopAudioManager,
  audioRoutingManager
}) {
  const repoRoot = path.join(baseDir, "..");

  ipcMain.handle("list-desktop-devices", async (_event, backend) => {
    return desktopAudioProbe.listDesktopDevices(backend);
  });

  ipcMain.handle("desktop-audio-manager-status", async () => {
    const stateDir = app.getPath("userData");
    return desktopAudioManager.getDesktopAudioManagerStatus(repoRoot, stateDir);
  });

  ipcMain.handle("desktop-audio-manager-install", async () => {
    const stateDir = app.getPath("userData");
    return desktopAudioManager.installDesktopAudioComponent(repoRoot, stateDir);
  });

  ipcMain.handle("desktop-audio-manager-download", async () => {
    const stateDir = app.getPath("userData");
    return desktopAudioManager.downloadDesktopAudioComponent(repoRoot, stateDir);
  });

  ipcMain.handle("desktop-audio-manager-uninstall", async () => {
    const stateDir = app.getPath("userData");
    return desktopAudioManager.uninstallDesktopAudioComponent(repoRoot, stateDir);
  });

  ipcMain.handle("desktop-audio-manager-reload-audio", async () => {
    const stateDir = app.getPath("userData");
    return desktopAudioManager.reloadDesktopAudioDevices(repoRoot, stateDir);
  });

  ipcMain.handle("audio-routing-status", async () => {
    const stateDir = app.getPath("userData");
    return audioRoutingManager.getAudioRoutingStatus(stateDir);
  });

  ipcMain.handle("audio-routing-apply", async () => {
    const stateDir = app.getPath("userData");
    return audioRoutingManager.applyDesktopAudioRouting(stateDir);
  });

  ipcMain.handle("audio-routing-restore", async () => {
    const stateDir = app.getPath("userData");
    return audioRoutingManager.restoreDesktopAudioRouting(stateDir);
  });
}

module.exports = { registerDesktopIpcHandlers };

