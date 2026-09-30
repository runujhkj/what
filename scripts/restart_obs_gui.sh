#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OS_NAME="$(uname -s)"

case "$OS_NAME" in
  Darwin)
    exec "$SCRIPT_DIR/restart_obs_gui.macos.sh" "$@"
    ;;
  Linux)
    exec "$SCRIPT_DIR/restart_obs_gui.linux.sh" "$@"
    ;;
  *)
    echo "error: unsupported OS '$OS_NAME' for restart_obs_gui.sh" >&2
    exit 1
    ;;
esac

