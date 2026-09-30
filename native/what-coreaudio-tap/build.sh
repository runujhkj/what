#!/bin/bash
# Build bin/what-coreaudio-tap.swift (SCStream-based desktop audio capture)
# into bin/WhatCoreAudioTap.app and install a LaunchAgent so the tap runs at
# login with its own TCC identity (com.what.coreaudio-tap), independent of Electron.
#
# On macOS 26 (Tahoe), TCC tracks responsibility via the audit session of the
# launching process — even 'open -n' called from Electron inherits Electron's
# session and gets only the ~45-60s grace period.  The LaunchAgent is started by
# launchd directly, with no Electron in its ancestry, so Screen Recording is
# granted indefinitely once the user allows it.
#
# Signing:
#   Default (no WHAT_SIGNING_IDENTITY set):
#     Ad-hoc signed. TCC keys by binary hash, so Screen Recording will
#     re-prompt after each rebuild. Rebuilds only happen when the Swift source
#     changes (bin/what-coreaudio-tap.swift).
#
#   WHAT_SIGNING_IDENTITY="Apple Development: you@example.com (TEAMID)"
#     Stable TCC grant across rebuilds. Requires an Apple Developer account.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

BUNDLE_ID="com.what.coreaudio-tap"
SWIFT_SRC="$REPO_ROOT/bin/what-coreaudio-tap.swift"
APP="$REPO_ROOT/bin/WhatCoreAudioTap.app"
APP_MACOS="$APP/Contents/MacOS"
APP_BINARY="$APP_MACOS/WhatCoreAudioTap"

IDENTITY="${WHAT_SIGNING_IDENTITY:-}"

# Compile
rm -rf "$APP"
mkdir -p "$APP_MACOS"

echo "Compiling $SWIFT_SRC ..."
swiftc \
    -framework ScreenCaptureKit \
    -framework CoreMedia \
    -framework Foundation \
    "$SWIFT_SRC" \
    -o "$APP_BINARY"

# Info.plist
cat > "$APP/Contents/Info.plist" << 'PLIST_EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleIdentifier</key>
    <string>com.what.coreaudio-tap</string>
    <key>CFBundleName</key>
    <string>WhatCoreAudioTap</string>
    <key>CFBundleDisplayName</key>
    <string>What System Audio</string>
    <key>CFBundleExecutable</key>
    <string>WhatCoreAudioTap</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>NSScreenCaptureUsageDescription</key>
    <string>What System Audio captures system audio to enable live transcription.</string>
    <key>LSUIElement</key>
    <true/>
    <key>LSMinimumSystemVersion</key>
    <string>13.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
PLIST_EOF

# Sign. Prefer a STABLE identity so the Screen-Recording grant survives rebuilds (ad-hoc
# changes the code hash every build -> macOS re-prompts each time). If WHAT_SIGNING_IDENTITY
# isn't set, auto-discover an Apple Development cert from the keychain; fall back to ad-hoc.
if [ -z "$IDENTITY" ]; then
    IDENTITY="$(security find-identity -v -p codesigning 2>/dev/null | awk -F'"' '/Apple Development/{print $2; exit}')"
    [ -n "$IDENTITY" ] && echo "Auto-discovered signing identity: $IDENTITY"
fi
if [ -z "$IDENTITY" ]; then
    codesign --sign - --identifier "$BUNDLE_ID" --force --deep "$APP"
    echo "Signed ad-hoc (no signing identity found; TCC will re-prompt if the binary changes)."
    echo "  -> set WHAT_SIGNING_IDENTITY or add an Apple Development cert to make grants persist."
else
    codesign \
        --sign "$IDENTITY" \
        --identifier "$BUNDLE_ID" \
        --entitlements "$SCRIPT_DIR/Entitlements.plist" \
        --options runtime \
        --force --deep \
        "$APP"
    echo "Signed with: $IDENTITY"
fi

FIXED_SOCKET="/tmp/what-coreaudio-tap.sock"
AGENT_LABEL="com.what.coreaudio-tap"
AGENT_PLIST="$HOME/Library/LaunchAgents/${AGENT_LABEL}.plist"

# LaunchAgent is now OPT-IN (WHAT_INSTALL_LAUNCHAGENT=1). It is NOT needed when the app
# starts the tap on demand -- and the old RunAtLoad+KeepAlive combo turned a
# single denied TCC prompt into an infinite respawn loop (KeepAlive re-launched the tap after
# every deny). When installed here it uses RunAtLoad only (no KeepAlive) so a denial exits
# once instead of looping.
if [ "${WHAT_INSTALL_LAUNCHAGENT:-0}" = "1" ]; then
    mkdir -p "$HOME/Library/LaunchAgents"
    cat > "$AGENT_PLIST" << AGENT_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${AGENT_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${APP_BINARY}</string>
        <string>--socket-path</string>
        <string>${FIXED_SOCKET}</string>
        <string>--persistent</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardErrorPath</key>
    <string>/tmp/what-coreaudio-tap.log</string>
</dict>
</plist>
AGENT_EOF
    echo "Installed opt-in LaunchAgent (RunAtLoad, no KeepAlive): $AGENT_PLIST"
else
    # Proactively retire a previously-installed looping agent so old installs stop re-prompting.
    if [ -f "$AGENT_PLIST" ]; then
        launchctl bootout "gui/$(id -u)/${AGENT_LABEL}" 2>/dev/null || true
        mv "$AGENT_PLIST" "${AGENT_PLIST}.disabled" 2>/dev/null || true
        echo "Retired the old LaunchAgent (set WHAT_INSTALL_LAUNCHAGENT=1 to reinstall)."
    fi
fi

echo ""
echo "Built: $APP"
echo ""
echo "SETUP:"
echo "  - The app starts this tap on demand when desktop capture begins --"
echo "    no LaunchAgent needed. Grant Screen Recording at the FIRST prompt (click Allow)."
echo "  - Grants persist across rebuilds only with a stable signing identity; ad-hoc re-prompts."
echo "  - Standalone persistent tap (optional): rebuild with WHAT_INSTALL_LAUNCHAGENT=1, then"
echo "       launchctl unload '$AGENT_PLIST' 2>/dev/null; launchctl load '$AGENT_PLIST'"
echo ""
echo "  To stop / uninstall:"
echo "       launchctl unload '$AGENT_PLIST'"
