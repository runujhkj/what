#!/usr/bin/env bash
set -euo pipefail

role="${1:-all}"

case "$role" in
  all)
    req="requirements.txt"
    ;;
  client)
    req="requirements-client.txt"
    ;;
  service)
    req="requirements-service.txt"
    ;;
  macos-service)
    req="requirements-macos-service.txt"
    ;;
  *)
    echo "Usage: $0 [all|client|service|macos-service]" >&2
    exit 2
    ;;
esac

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found on PATH" >&2
  exit 1
fi

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r "$req"

echo "Setup complete."
echo "Activate with: source .venv/bin/activate"
