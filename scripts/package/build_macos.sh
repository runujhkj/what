#!/usr/bin/env bash
# Build the macOS (Apple Silicon) app: gui/dist/what-<version>-arm64.dmg and .zip.
#
#   scripts/package/build_macos.sh            # dmg + zip
#   scripts/package/build_macos.sh dir        # just gui/dist/mac-arm64/What.app, for testing
#
# Steps:
#   1. Python runtime: a relocatable CPython (python-build-standalone) with the macOS
#      dependencies preinstalled, so users need no Python of their own.
#   2. FFmpeg: a static arm64 ffmpeg for microphone capture.
#   3. Native helpers: the WhisperKit ASR worker (swift build) and WhatCoreAudioTap.app.
#   4. electron-builder. Without a Developer ID the app is ad-hoc signed (gui/build-hooks/);
#      with CSC_LINK/CSC_KEY_PASSWORD electron-builder signs it instead. See
#      docs/packaging_macos.md.
#
# Needs an Apple-silicon Mac with Xcode (Swift 6+), Node.js/npm and curl.
set -euo pipefail

target="${1:-dist}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
gui="$root/gui"
build="$gui/build"
pins="$root/scripts/package/macos_pins.json"
pin() { node -e "console.log(require(process.argv[1])[process.argv[2]].url)" "$pins" "$1"; }

[ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ] || { echo "ERROR: needs an Apple-silicon Mac" >&2; exit 1; }
mkdir -p "$build/downloads" "$build/bin"

fetch() { # url dest
  [ -f "$2" ] || { echo "Downloading $1"; curl -fsSL --retry 3 -o "$2.part" "$1" && mv "$2.part" "$2"; }
}

echo "==> Staging Python source"
bash "$root/scripts/package/prepare_python_runtime.sh" "$build/pyruntime"

echo "==> Staging Python runtime"
py="$build/python"
if [ ! -f "$py/.what-deps" ]; then
  archive="$build/downloads/$(basename "$(pin python)")"
  fetch "$(pin python)" "$archive"
  rm -rf "$py" "$build/python-extract"
  mkdir -p "$build/python-extract"
  tar -xzf "$archive" -C "$build/python-extract"
  mv "$build/python-extract/python" "$py"
  rm -rf "$build/python-extract"
  # Same dependency list as the first-run venv on Linux (gui/lib/python_runtime.js).
  deps=()
  while IFS= read -r d; do deps+=("$d"); done < <(node -e "require(process.argv[1]).DEPENDENCIES.forEach(d => console.log(d))" "$gui/lib/python_runtime.js")
  "$py/bin/python3" -m pip install --disable-pip-version-check "${deps[@]}"
  "$py/bin/python3" -c "import webrtcvad, fastapi, uvicorn, websockets, zeroconf, numpy; print('python deps ok')"
  find "$py" -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
  date -u +%FT%TZ > "$py/.what-deps"
fi

echo "==> Staging FFmpeg"
if [ ! -x "$build/bin/ffmpeg" ]; then
  gz="$build/downloads/$(basename "$(pin ffmpeg)")"
  fetch "$(pin ffmpeg)" "$gz"
  gunzip -c "$gz" > "$build/bin/ffmpeg"
  chmod +x "$build/bin/ffmpeg"
fi
"$build/bin/ffmpeg" -hide_banner -f avfoundation -list_devices true -i "" 2>&1 | head -3 || true

echo "==> Building the WhisperKit worker"
(cd "$root/native/WhisperKitWorker" && swift build -c release)
cp "$root/native/WhisperKitWorker/.build/release/what-whisperkit-worker" "$build/bin/"

echo "==> Building the desktop-audio tap"
# build.sh writes bin/WhatCoreAudioTap.app under the repo; it only installs a LaunchAgent
# when WHAT_INSTALL_LAUNCHAGENT=1 (not set here).
bash "$root/native/what-coreaudio-tap/build.sh"
rm -rf "$build/bin/WhatCoreAudioTap.app"
cp -R "$root/bin/WhatCoreAudioTap.app" "$build/bin/"

echo "==> electron-builder"
cd "$gui"
npm ci
extra=()
if [ -n "${CSC_LINK:-}" ]; then
  # Developer ID signing: the hardened runtime is required for notarization.
  extra+=("-c.mac.hardenedRuntime=true")
  [ -n "${APPLE_ID:-}" ] && extra+=("-c.mac.notarize=true")  # needs APPLE_APP_SPECIFIC_PASSWORD, APPLE_TEAM_ID
fi
if [ "$target" = "dir" ]; then
  npx electron-builder --mac dir --arm64 --publish never ${extra[@]+"${extra[@]}"}
else
  npx electron-builder --mac dmg zip --arm64 --publish never ${extra[@]+"${extra[@]}"}
fi
ls -la dist
