#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OBS_SOURCE_DIR="$REPO_ROOT/obs-plugin"
OBS_BUILD_DIR="$OBS_SOURCE_DIR/build"
PLUGIN_SRC_BUNDLE="$OBS_BUILD_DIR/what_overlay_plugin.plugin"
PLUGIN_DST="$HOME/Library/Application Support/obs-studio/plugins"
WHAT_BIN="${WHAT_BIN:-$REPO_ROOT/_venv/bin/what}"
DO_OBS=1
DO_API_GUI=1
DO_CAPTURE=1
DEBUG_PLUGIN=0
GUI_MODE="main"
OBS_FORCE_KILL="${WHAT_OBS_FORCE_KILL:-1}"
CONTROL_BASE_URL="${WHAT_CONTROL_BASE_URL:-http://127.0.0.1:8780}"

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

ensure_macos_electron_runtime() {
  local mac_electron="$REPO_ROOT/gui/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron"
  if [[ -x "$mac_electron" ]] && file "$mac_electron" | grep -q "Mach-O"; then
    return 0
  fi
  log "[4a/5] Detected missing/mismatched macOS Electron runtime; rebuilding electron..."
  npm --prefix "$REPO_ROOT/gui" rebuild electron || true
  if [[ -x "$mac_electron" ]] && file "$mac_electron" | grep -q "Mach-O"; then
    return 0
  fi

  log "[4b/5] Electron runtime still invalid; reinstalling electron package..."
  rm -rf "$REPO_ROOT/gui/node_modules/electron" "$REPO_ROOT/gui/node_modules/.bin/electron"
  npm --prefix "$REPO_ROOT/gui" install --force --foreground-scripts
  if [[ ! -x "$mac_electron" ]] || ! file "$mac_electron" | grep -q "Mach-O"; then
    echo "error: macOS Electron runtime still missing after install: $mac_electron" >&2
    return 1
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

print_proc() {
  local pid="$1"
  if [[ -n "$pid" ]] && ps -p "$pid" -o pid=,ppid=,stat=,etime=,command= >/dev/null 2>&1; then
    ps -p "$pid" -o pid=,ppid=,stat=,etime=,command=
  fi
}

pid_in_list() {
  local needle="$1"
  shift || true
  local p
  for p in "$@"; do
    if [[ "$p" == "$needle" ]]; then
      return 0
    fi
  done
  return 1
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

if [[ "$DO_OBS" -eq 1 ]]; then
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
  mkdir -p "$PLUGIN_DST"
  rm -rf "$PLUGIN_DST/what_overlay_plugin.plugin"
  cp -R "$PLUGIN_SRC_BUNDLE" "$PLUGIN_DST/"

  log "[3/5] Restarting OBS..."
  OBS_BEFORE_ARR=()
  while IFS= read -r pid; do
    [[ -n "$pid" ]] && OBS_BEFORE_ARR+=("$pid")
  done < <(pgrep -x OBS || true)
  OBS_BEFORE="$(printf "%s " "${OBS_BEFORE_ARR[@]:-}" | xargs || true)"
  osascript -e 'tell application "OBS" to quit' >/dev/null 2>&1 || true
  for _ in {1..80}; do
    if ! pgrep -x OBS >/dev/null 2>&1; then
      break
    fi
    sleep 0.25
  done
  if pgrep -x OBS >/dev/null 2>&1; then
    log "OBS did not quit via AppleScript; sending TERM..."
    pkill -TERM -x OBS >/dev/null 2>&1 || true
    for _ in {1..24}; do
      if ! pgrep -x OBS >/dev/null 2>&1; then
        break
      fi
      sleep 0.25
    done
    if pgrep -x OBS >/dev/null 2>&1; then
      if [[ "$OBS_FORCE_KILL" == "1" ]]; then
        log "OBS still running; forcing KILL (WHAT_OBS_FORCE_KILL=1)..."
        pkill -KILL -x OBS >/dev/null 2>&1 || true
        sleep 0.5
      else
        log "warning: OBS still running after TERM and force-kill disabled; restart may be partial."
      fi
    fi
  fi
  if pgrep -x OBS >/dev/null 2>&1; then
    pkill -KILL -x OBS >/dev/null 2>&1 || true
    sleep 0.4
  fi
  sleep 0.6
  open -a OBS
  OBS_PID=""
  for _ in {1..20}; do
    OBS_AFTER_ARR=()
    while IFS= read -r pid; do
      [[ -n "$pid" ]] && OBS_AFTER_ARR+=("$pid")
    done < <(pgrep -x OBS || true)
    OBS_PID=""
    for candidate in "${OBS_AFTER_ARR[@]:-}"; do
      if ! pid_in_list "$candidate" "${OBS_BEFORE_ARR[@]:-}"; then
        OBS_PID="$candidate"
        break
      fi
    done
    if [[ -z "$OBS_PID" && "${#OBS_AFTER_ARR[@]}" -gt 0 ]]; then
      OBS_PID="${OBS_AFTER_ARR[0]}"
    fi
    if [[ -n "$OBS_PID" ]]; then
      break
    fi
    sleep 0.5
  done
  if [[ -n "$OBS_PID" ]]; then
    OBS_CHANGED="yes"
    if [[ -n "${OBS_BEFORE:-}" ]]; then
      if pid_in_list "$OBS_PID" "${OBS_BEFORE_ARR[@]:-}"; then
        OBS_CHANGED="no"
      fi
    fi
    log "OBS PID (before): ${OBS_BEFORE:-none}"
    log "OBS PID (after):  $OBS_PID"
    log "OBS PID changed:  $OBS_CHANGED"
    log "OBS process: $(print_proc "$OBS_PID")"
  else
    log "warning: OBS launch not observed via pgrep"
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
  ensure_macos_electron_runtime
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
  kill_matching "gui/node_modules/electron/.*/Electron.app/Contents/MacOS/Electron"

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
  log "what gui PID: $WHAT_GUI_PID"
  log "what gui process: $(print_proc "$WHAT_GUI_PID")"
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
