#!/usr/bin/env bash
set -euo pipefail

echo "==> CLI help"
python -m what --help >/dev/null

echo "==> Service help"
python -m what service --help >/dev/null

echo "==> GPU endpoint (requires service running)"
echo "Run: curl http://127.0.0.1:8765/gpu"

echo "==> Stats endpoint (requires service running and audio flowing)"
echo "Run: curl http://127.0.0.1:8765/stats"

echo "Smoke checks completed."
