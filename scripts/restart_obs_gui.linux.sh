#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OBS_SOURCE_DIR="$REPO_ROOT/obs-plugin"
OBS_BUILD_DIR="$OBS_SOURCE_DIR/build"
PLUGIN_SRC_SO="$OBS_BUILD_DIR/what_overlay_plugin.so"
WHAT_BIN="${WHAT_BIN:-$REPO_ROOT/_venv/bin/what}"
DO_OBS=1
DO_API_GUI=1
DO_CAPTURE=1
DEBUG_PLUGIN=0
GUI_MODE="main"
CONTROL_BASE_URL="${WHAT_CONTROL_BASE_URL:-http://127.0.0.1:8780}"

WHAT_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/what"
KNOWN_OBS_FILE="$WHAT_CONFIG_DIR/obs_target.env"
PLUGIN_DST=""
OBS_CMD_STR=""
OBS_CMD_ARR=()

usage() {
  cat <<'EOF'
Usage: restart_obs_gui.sh [-o] [-a] [-d] [-c]

  -o    Only rebuild/reinstall plugin and restart OBS.
  -a    Only restart what gui (API GUI).
  -d    Restart desktop-audio component stub GUI only.
  -c    Restart desktop-audio component stub GUI + capture sidecar.
  -D    Reconfigure/rebuild OBS plugin with WHAT_OVERLAY_DEBUG=ON.
EOF
}

log() {
  echo "$@"
}

linux_path_has_file() {
  local rel="$1"
  local base=""
  for base in /usr/include /usr/local/include; do
    if [[ -f "$base/$rel" ]]; then
      return 0
    fi
  done
  return 1
}

require_linux_obs_dev_deps() {
  local missing=0
  if ! linux_path_has_file "obs/obs-module.h"; then
    echo "error: OBS development headers not found (missing obs/obs-module.h)." >&2
    echo "hint: install OBS dev files (Ubuntu example: sudo apt install libobs-dev)." >&2
    missing=1
  fi
  if ! linux_path_has_file "simde/x86/sse2.h"; then
    echo "error: required SIMD headers not found (missing simde/x86/sse2.h)." >&2
    echo "hint: install SIMDe dev files (Ubuntu example: sudo apt install libsimde-dev)." >&2
    missing=1
  fi
  if [[ "$missing" -ne 0 ]]; then
    exit 1
  fi
}

require_gui_runtime() {
  local electron_linux="$REPO_ROOT/gui/node_modules/electron/dist/electron"
  if [[ -x "$electron_linux" ]]; then
    return 0
  fi
  log "[4a/5] Detected missing/mismatched Linux Electron runtime; reinstalling gui deps..."
  npm --prefix "$REPO_ROOT/gui" install
  if [[ ! -x "$electron_linux" ]]; then
    echo "error: Linux Electron runtime still missing after install: $electron_linux" >&2
    echo "hint: install GUI deps when online: (cd gui && npm install)" >&2
    exit 1
  fi
}

kill_matching() {
  local pattern="$1"
  if pgrep -f "$pattern" >/dev/null 2>&1; then
    pkill -TERM -f "$pattern" >/dev/null 2>&1 || true
    sleep 0.5
    pkill -KILL -f "$pattern" >/dev/null 2>&1 || true
  fi
}

kill_port_listener() {
  local port="$1"
  local pids
  pids="$(lsof -ti "tcp:${port}" 2>/dev/null || true)"
  if [[ -z "${pids}" ]]; then
    return
  fi
  # shellcheck disable=SC2086
  kill -TERM ${pids} >/dev/null 2>&1 || true
  sleep 0.4
  # shellcheck disable=SC2086
  kill -KILL ${pids} >/dev/null 2>&1 || true
}

detect_obs_target() {
  local native_plugin="$HOME/.local/share/obs-studio/plugins"
  local flatpak_plugin="$HOME/.var/app/com.obsproject.Studio/config/obs-studio/plugins"
  if command -v obs >/dev/null 2>&1; then
    PLUGIN_DST="$native_plugin"
    OBS_CMD_STR="obs"
    return 0
  fi
  if command -v obs-studio >/dev/null 2>&1; then
    PLUGIN_DST="$native_plugin"
    OBS_CMD_STR="obs-studio"
    return 0
  fi
  if [[ -d "$HOME/.var/app/com.obsproject.Studio" ]]; then
    PLUGIN_DST="$flatpak_plugin"
    OBS_CMD_STR="flatpak run com.obsproject.Studio"
    return 0
  fi
  return 1
}

load_known_obs_target() {
  if [[ -f "$KNOWN_OBS_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$KNOWN_OBS_FILE"
  fi
  if [[ -n "${OBS_CMD_STR:-}" ]]; then
    read -r -a OBS_CMD_ARR <<< "$OBS_CMD_STR"
  fi
}

save_known_obs_target() {
  mkdir -p "$WHAT_CONFIG_DIR"
  cat >"$KNOWN_OBS_FILE" <<EOF
PLUGIN_DST="${PLUGIN_DST}"
OBS_CMD_STR="${OBS_CMD_STR}"
EOF
}

while getopts ":oacDdh" opt; do
  case "$opt" in
    o) DO_OBS=1; DO_API_GUI=0; DO_CAPTURE=0 ;;
    a) DO_OBS=0; DO_API_GUI=1; DO_CAPTURE=0 ;;
    d) DO_OBS=0; DO_API_GUI=1; DO_CAPTURE=0; GUI_MODE="desktop-audio-stub" ;;
    c) DO_OBS=0; DO_API_GUI=1; DO_CAPTURE=1; GUI_MODE="desktop-audio-stub" ;;
    D) DEBUG_PLUGIN=1 ;;
    h) usage; exit 0 ;;
    :) echo "error: option -$OPTARG requires an argument" >&2; usage >&2; exit 2 ;;
    \?) echo "error: invalid option -$OPTARG" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ "${*:-}" == *"-o"* && "${*:-}" == *"-a"* ]]; then
  DO_OBS=1
  DO_API_GUI=1
  DO_CAPTURE=1
fi

wait_for_control_ready() {
  local deadline=$((SECONDS + 10))
  while (( SECONDS < deadline )); do
    if curl -fsS --max-time 1 "$CONTROL_BASE_URL/control/status" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.25
  done
  return 1
}

restart_desktop_capture_sidecar() {
  if ! command -v curl >/dev/null 2>&1; then
    echo "error: curl is required for desktop capture restart mode" >&2
    return 1
  fi
  if ! wait_for_control_ready; then
    echo "error: control api not reachable at $CONTROL_BASE_URL (is what gui running?)" >&2
    return 1
  fi
  local stop_resp=""
  local start_resp=""
  local start_payload='{"capture_mode":"native-capture"}'
  if [[ "$GUI_MODE" == "desktop-audio-stub" ]]; then
    start_payload='{"capture_mode":"native-capture","no_stream":true}'
  fi
  stop_resp="$(curl -sS --max-time 3 -X POST "$CONTROL_BASE_URL/control/native-desktop-helper/stop" || true)"
  start_resp="$(curl -sS --max-time 8 -X POST "$CONTROL_BASE_URL/control/native-desktop-helper/start" -H 'Content-Type: application/json' -d "$start_payload" || true)"
  log "desktop capture stop:  ${stop_resp:-<no-response>}"
  log "desktop capture start: ${start_resp:-<no-response>}"
}

load_known_obs_target
if [[ -z "${PLUGIN_DST:-}" || -z "${OBS_CMD_STR:-}" ]]; then
  if ! detect_obs_target; then
    echo "error: could not detect OBS install; set PLUGIN_DST/OBS_CMD_STR in $KNOWN_OBS_FILE" >&2
    exit 1
  fi
  save_known_obs_target
  read -r -a OBS_CMD_ARR <<< "$OBS_CMD_STR"
fi

if [[ "$DO_OBS" -eq 1 ]]; then
  require_linux_obs_dev_deps
  if [[ "$DEBUG_PLUGIN" -eq 1 ]]; then
    log "[0/5] Configuring OBS plugin with WHAT_OVERLAY_DEBUG=ON..."
    cmake -S "$OBS_SOURCE_DIR" -B "$OBS_BUILD_DIR" -DWHAT_OVERLAY_DEBUG=ON
  elif [[ ! -f "$OBS_BUILD_DIR/CMakeCache.txt" ]]; then
    log "[0/5] Configuring OBS plugin..."
    cmake -S "$OBS_SOURCE_DIR" -B "$OBS_BUILD_DIR"
  fi

  log "[1/5] Building OBS plugin..."
  cmake --build "$OBS_BUILD_DIR"

  log "[2/5] Installing plugin..."
  if [[ ! -f "$PLUGIN_SRC_SO" ]]; then
    echo "error: built Linux plugin library not found: $PLUGIN_SRC_SO" >&2
    exit 1
  fi
  mkdir -p "$PLUGIN_DST/what_overlay_plugin/bin/64bit"
  cp -f "$PLUGIN_SRC_SO" "$PLUGIN_DST/what_overlay_plugin/bin/64bit/what_overlay_plugin.so"

  log "[3/5] Restarting OBS..."
  kill_matching "^obs$"
  kill_matching "^obs-studio$"
  kill_matching "com.obsproject.Studio"
  sleep 1
  if [[ "${#OBS_CMD_ARR[@]}" -gt 0 ]]; then
    nohup "${OBS_CMD_ARR[@]}" >/tmp/what-obs.log 2>&1 &
  else
    log "warning: OBS launch command not known; install completed but OBS not started."
  fi
else
  log "[1-3/5] Skipping OBS/plugin flow (-a mode)"
fi

if [[ "$DO_API_GUI" -eq 1 ]]; then
  if [[ "$GUI_MODE" == "desktop-audio-stub" ]]; then
    log "[4/5] Restarting desktop-audio stub gui..."
  else
    log "[4/5] Restarting what gui..."
  fi
  require_gui_runtime
  if [[ ! -x "$WHAT_BIN" ]]; then
    echo "error: what binary not executable: $WHAT_BIN" >&2
    exit 1
  fi
  kill_port_listener 8780
  kill_port_listener 8765
  kill_matching "_venv/bin/what gui"
  kill_matching "/what gui"
  kill_matching "_venv/bin/what control"
  kill_matching "/what control"
  kill_matching "_venv/bin/what service"
  kill_matching "/what service"
  kill_matching "/projects/what/gui/main.js"
  kill_matching "gui/node_modules/electron/.*/dist/electron"
  sleep 1
  if [[ "$GUI_MODE" == "desktop-audio-stub" ]]; then
    nohup env \
      WHAT_GUI_MODE=desktop-audio-stub \
      WHAT_DESKTOP_ROUTING_ENABLE="${WHAT_DESKTOP_ROUTING_ENABLE:-1}" \
      WHAT_DESKTOP_ROUTING_BACKEND="${WHAT_DESKTOP_ROUTING_BACKEND:-coreaudio_aggregate}" \
      "$WHAT_BIN" gui >/tmp/what-gui.log 2>&1 &
  else
    nohup env \
      WHAT_DESKTOP_ROUTING_ENABLE="${WHAT_DESKTOP_ROUTING_ENABLE:-1}" \
      WHAT_DESKTOP_ROUTING_BACKEND="${WHAT_DESKTOP_ROUTING_BACKEND:-coreaudio_aggregate}" \
      "$WHAT_BIN" gui >/tmp/what-gui.log 2>&1 &
  fi
  WHAT_GUI_PID=$!
  sleep 1
  if ! kill -0 "$WHAT_GUI_PID" >/dev/null 2>&1; then
    echo "error: what gui exited immediately; see /tmp/what-gui.log" >&2
    tail -n 80 /tmp/what-gui.log >&2 || true
    exit 1
  fi
else
  log "[4/5] Skipping what gui flow (-o mode)"
fi

if [[ "$DO_CAPTURE" -eq 1 ]]; then
  log "[5/6] Restarting desktop capture sidecar..."
  restart_desktop_capture_sidecar
else
  log "[5/6] Skipping desktop capture sidecar restart."
fi

log "[6/6] Done."
if [[ "$DO_API_GUI" -eq 1 ]]; then
  log "what gui log: /tmp/what-gui.log"
fi
