function loadUiPrefsDisk(fs, filePath) {
  try {
    const raw = fs.readFileSync(filePath, "utf-8");
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch (_err) {
    return {};
  }
}

function saveUiPrefsDisk(fs, path, filePath, prefs) {
  try {
    const data = prefs && typeof prefs === "object" ? prefs : {};
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, JSON.stringify(data, null, 2), "utf-8");
    return { ok: true };
  } catch (err) {
    return { ok: false, error: String(err) };
  }
}

module.exports = {
  loadUiPrefsDisk,
  saveUiPrefsDisk
};
