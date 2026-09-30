# macOS packaging (Apple Silicon)

Status: **written but not yet run.** It was authored without access to a Mac. The first
`macos` job of the Release workflow is the first real build; expect to fix things.

`scripts/package/build_macos.sh` builds `gui/dist/what-<version>-arm64.dmg` and
`what-<version>-arm64-mac.zip` (run on an Apple-silicon Mac with Xcode 16+/Swift 6, or via
the `macos` job in `.github/workflows/release.yml`). It:

1. stages the `what` source (`prepare_python_runtime.sh`) and a relocatable CPython with the
   app's dependencies (pins in `macos_pins.json`), bundled as `Resources/python`, which
   `gui/lib/runtime_paths.js` already prefers over a first-run venv;
2. bundles a static arm64 `ffmpeg`, the `what-whisperkit-worker` binary
   (found through `WHAT_WHISPERKIT_WORKER`, set in `gui/main.js`) and `WhatCoreAudioTap.app`
   (used in place of building it on first run) under `Resources/bin`;
3. runs electron-builder (`gui/package.json` → `build.mac`).

## Signing

There is no Developer ID, so the build is **ad-hoc signed** (`gui/build-hooks/adhoc-sign.js`,
needed because Apple-silicon Macs refuse a bundle with a broken signature; the build
checks it with `codesign --verify`). Gatekeeper blocks the downloaded app on first launch
with a "could not verify" / Move to Trash dialog. After **Open Anyway**, the first launch was
observed to hang: the process sat at `_dyld_start` (0% CPU, nothing loaded) while the bundle
was still quarantined, and it launched immediately once `xattr -dr com.apple.quarantine`
cleared the flag. The README therefore leads with the `xattr` command. To make that check
cheaper the build leaves out faster-whisper (unused on Apple Silicon) and unused parts of
CPython (tests, Tk). The Screen Recording grant for the tap can also reset when the app
is updated.

To sign and notarize properly you need the Apple Developer Program (US$99/year). Then add
these repository secrets; the workflow and script pick them up with no other change:
`CSC_LINK` (base64 of the Developer ID Application `.p12`), `CSC_KEY_PASSWORD`, and for
notarization `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`, `APPLE_TEAM_ID`.

## Known gaps / to verify

- Launch the built app on a clean Mac; check the model download, mic capture, desktop capture
  (Screen Recording prompt for "What System Audio") and replay.
- The bundled ffmpeg must list avfoundation devices; the build prints the first lines.
- Whether notarization (Developer ID) also removes the first-launch hang; it should, as
  notarized apps skip most of the local assessment.
- The WhisperKit model (`base`) downloads on first start; it is not pre-provisioned.
- Apple Silicon only; no Intel build.
