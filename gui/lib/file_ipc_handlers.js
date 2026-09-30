function registerFileIpcHandlers({ ipcMain, dialog, fs, path, baseDir }) {
  ipcMain.handle("pick-audio-file", async () => {
    const result = await dialog.showOpenDialog({
      title: "Select audio file",
      properties: ["openFile"],
      filters: [
        { name: "Audio", extensions: ["wav", "mp3", "m4a", "flac", "ogg", "opus", "aac"] },
        { name: "All Files", extensions: ["*"] }
      ]
    });
    if (result.canceled || result.filePaths.length === 0) {
      return null;
    }
    return result.filePaths[0];
  });

  ipcMain.handle("pick-corrections-bundle", async () => {
    const result = await dialog.showOpenDialog({
      title: "Select corrections bundle",
      properties: ["openFile"],
      filters: [
        { name: "JSONL", extensions: ["jsonl"] },
        { name: "All Files", extensions: ["*"] }
      ]
    });
    if (result.canceled || result.filePaths.length === 0) {
      return null;
    }
    return result.filePaths[0];
  });

  ipcMain.handle("pick-obs-output", async () => {
    const result = await dialog.showSaveDialog({
      title: "Select OBS output file",
      defaultPath: path.join(baseDir, "..", "output", "what_obs.txt"),
      filters: [{ name: "Text", extensions: ["txt"] }, { name: "All Files", extensions: ["*"] }]
    });
    if (result.canceled || !result.filePath) {
      return null;
    }
    return result.filePath;
  });

  ipcMain.handle("list-audio-files", async () => {
    const repoRoot = path.join(baseDir, "..");
    const audioDir = path.join(repoRoot, "audio");
    const entries = [];
    try {
      const files = fs.readdirSync(audioDir);
      files.forEach((name) => {
        if (!name.toLowerCase().endsWith(".wav")) return;
        const full = path.join(audioDir, name);
        entries.push({
          path: full,
          label: `audio/${name}`
        });
      });
    } catch (_err) {
      return entries;
    }
    return entries;
  });
}

module.exports = {
  registerFileIpcHandlers
};
