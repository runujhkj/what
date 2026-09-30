function registerCorrectionsIpcHandlers({
  ipcMain,
  fs,
  path,
  baseDir,
  spawnSync,
  env
}) {
  const repoRoot = path.join(baseDir, "..");

  ipcMain.handle("append-correction", async (_event, payload) => {
    if (!payload || !payload.session_id) {
      return { ok: false, error: "missing session_id" };
    }
    const dir = path.join(repoRoot, "corrections");
    try {
      fs.mkdirSync(dir, { recursive: true });
    } catch (err) {
      return { ok: false, error: String(err) };
    }
    const filePath = path.join(dir, `${payload.session_id}.jsonl`);
    const record = { ...payload, recorded_at: new Date().toISOString() };
    try {
      fs.appendFileSync(filePath, JSON.stringify(record) + "\n");
      return { ok: true, path: filePath };
    } catch (err) {
      return { ok: false, error: String(err) };
    }
  });

  ipcMain.handle("export-corrections-meta", async (_event, payload) => {
    const dir = path.join(repoRoot, "corrections");
    try {
      fs.mkdirSync(dir, { recursive: true });
    } catch (err) {
      return { ok: false, error: String(err) };
    }
    const filePath = path.join(dir, "export_meta.json");
    const record = {
      ...payload,
      recorded_at: new Date().toISOString()
    };
    try {
      fs.writeFileSync(filePath, JSON.stringify(record, null, 2));
      return { ok: true, path: filePath };
    } catch (err) {
      return { ok: false, error: String(err) };
    }
  });

  ipcMain.handle("export-corrections-bundle", async (_event, payload) => {
    const correctionsDir = path.join(repoRoot, "corrections");
    const exportDir = payload?.export_dir ? payload.export_dir : correctionsDir;
    const meId = payload?.me_speaker_id || "me";
    const instanceId = payload?.instance_id || "default";
    const notes = payload?.notes || "";
    try {
      const python = env.WHAT_PYTHON || path.join(repoRoot, "_venv", "bin", "python");
      const script = path.join(repoRoot, "what", "scripts", "export_corrections.py");
      const args = [
        script,
        "--corrections-dir",
        correctionsDir,
        "--export-dir",
        exportDir,
        "--me",
        meId,
        "--instance-id",
        instanceId,
        "--notes",
        notes
      ];
      const result = spawnSync(python, args, { encoding: "utf-8" });
      if (result.status !== 0) {
        return { ok: false, error: result.stderr || result.stdout || "export failed" };
      }
      return JSON.parse(result.stdout || "{}");
    } catch (err) {
      return { ok: false, error: String(err) };
    }
  });

  ipcMain.handle("import-corrections-bundle", async (_event, payload) => {
    const outDir = path.join(repoRoot, "corrections", "imported");
    const bundlePath = payload?.bundle_path;
    const speakerMap = payload?.speaker_map || {};
    if (!bundlePath) {
      return { ok: false, error: "missing bundle_path" };
    }
    try {
      const python = env.WHAT_PYTHON || path.join(repoRoot, "_venv", "bin", "python");
      const script = path.join(repoRoot, "what", "scripts", "import_corrections.py");
      const args = [
        script,
        "--bundle",
        bundlePath,
        "--out-dir",
        outDir,
        "--map",
        JSON.stringify(speakerMap)
      ];
      const result = spawnSync(python, args, { encoding: "utf-8" });
      if (result.status !== 0) {
        return { ok: false, error: result.stderr || result.stdout || "import failed" };
      }
      return JSON.parse(result.stdout || "{}");
    } catch (err) {
      return { ok: false, error: String(err) };
    }
  });

  ipcMain.handle("write-obs-output", async (_event, payload) => {
    const outPath = payload?.path
      ? payload.path
      : path.join(repoRoot, "output", "what_obs.txt");
    const text = payload?.text ?? "";
    try {
      fs.mkdirSync(path.dirname(outPath), { recursive: true });
      fs.writeFileSync(outPath, text, "utf-8");
      return { ok: true, path: outPath };
    } catch (err) {
      return { ok: false, error: String(err) };
    }
  });
}

module.exports = {
  registerCorrectionsIpcHandlers
};
