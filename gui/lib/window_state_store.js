function loadWindowStateFromDisk(fs, filePath, fallback) {
  const defaultState = fallback && typeof fallback === "object"
    ? fallback
    : { width: 900, height: 700 };
  try {
    const raw = fs.readFileSync(filePath, "utf-8");
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return defaultState;
    const width = Number(parsed.width);
    const height = Number(parsed.height);
    const x = Number(parsed.x);
    const y = Number(parsed.y);
    const out = {
      width: Number.isFinite(width) && width > 200 ? width : defaultState.width,
      height: Number.isFinite(height) && height > 200 ? height : defaultState.height
    };
    if (Number.isFinite(x) && Number.isFinite(y)) {
      out.x = x;
      out.y = y;
    }
    return out;
  } catch (_err) {
    return defaultState;
  }
}

// Drop a saved position that would put the window's title bar on no current display (for
// example a monitor that has since been unplugged); the window then opens centered.
// workAreas: [{ x, y, width, height }] from electron's screen.getAllDisplays().
function fitToDisplays(state, workAreas) {
  if (!state || !Number.isFinite(state.x) || !Number.isFinite(state.y)) return state;
  const areas = Array.isArray(workAreas) ? workAreas : [];
  const titleBar = { x: state.x, y: state.y, width: state.width, height: 40 };
  const visible = areas.some((a) =>
    titleBar.x + 100 <= a.x + a.width && titleBar.x + titleBar.width - 100 >= a.x &&
    titleBar.y < a.y + a.height && titleBar.y + titleBar.height > a.y);
  if (visible) return state;
  const { x, y, ...rest } = state;
  return rest;
}

function saveWindowStateToDisk(fs, path, filePath, win) {
  if (!win || (typeof win.isDestroyed === "function" && win.isDestroyed())) return;
  try {
    const bounds = win.getBounds();
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, JSON.stringify(bounds), "utf-8");
  } catch (_err) {
    // ignore
  }
}

module.exports = {
  loadWindowStateFromDisk,
  fitToDisplays,
  saveWindowStateToDisk
};
