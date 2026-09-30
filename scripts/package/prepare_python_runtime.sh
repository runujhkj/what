#!/usr/bin/env bash
# Stage the Python side of the app for electron-builder's extraResources.
#
# The AppImage bundles the `what` package source, config, and requirements read-only under
# resources/pyruntime. It does NOT bundle a virtualenv or the model weights: the app
# provisions a venv in the user's data dir on first run (see docs/packaging_linux.md), which
# keeps the image small and side-steps relocating a venv's absolute interpreter paths.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
dest="${1:-$repo_root/gui/build/pyruntime}"

echo "staging python runtime -> $dest"
rm -rf "$dest"
mkdir -p "$dest"

# Source package and its data. --prune keeps caches/build junk out of the image.
cp -R "$repo_root/what" "$dest/what"
cp -R "$repo_root/config" "$dest/config"
cp "$repo_root/pyproject.toml" "$dest/pyproject.toml"
for req in requirements.txt requirements-service.txt requirements-client.txt; do
  [ -f "$repo_root/$req" ] && cp "$repo_root/$req" "$dest/$req"
done

# Drop bytecode caches so the staged tree is deterministic and small.
find "$dest" -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
find "$dest" -type f -name "*.pyc" -delete 2>/dev/null || true

echo "staged $(find "$dest" -type f | wc -l) files"
