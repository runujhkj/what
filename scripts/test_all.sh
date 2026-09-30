#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -x "_venv/bin/pytest" ]]; then
  PYTEST="_venv/bin/pytest"
else
  PYTEST="pytest"
fi

echo "[test_all] running full pytest suite"
if [[ "${WHAT_SKIP_LIVE_DESKTOP_TESTS:-}" == "1" ]]; then
  echo "[test_all] live desktop tests disabled via WHAT_SKIP_LIVE_DESKTOP_TESTS=1"
fi

"$PYTEST" -q "$@"
