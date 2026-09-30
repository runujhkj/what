# what OBS Plugin

> Current browser integration: [What Caption Box](BROWSER_CAPTION_BOX.md) implements the shared renderer wrapper and drag-to-reflow. Build and adapter tests pass; live OBS validation is pending. The legacy native source remains available. The notes below describe that older implementation and its history; they do not define current product scope. See the [project brief](../docs/PROJECT_BRIEF.md).

This is a minimal, modular skeleton for an OBS source plugin that renders the
`what` caption stream natively inside OBS. It is not yet wired to OBS SDK.

## Goals
- Provide a native OBS source with a Properties panel (header, font size, colors, etc.)
- Consume the local overlay stream (SSE or WebSocket) from `what`
- Avoid WebView / Browser Source dependency

## Layout
```
obs-plugin/
  CMakeLists.txt
  include/
    what_overlay/
      overlay_client.h
      overlay_config.h
      layout/
        font_metrics.h
        line_layout.h
      overlay_state.h
      overlay_source.h
  src/
    layout/
      font_metrics.cpp
      line_layout.cpp
    overlay_client.cpp
    overlay_config.cpp
    overlay_state.cpp
    overlay_source.cpp
    plugin.cpp
```

## Build (macOS using OBS.app frameworks)
This skeleton can build against the installed OBS app frameworks (no source build required).

Default paths:
- `OBS_INCLUDE_DIR`: `~/projects/obs-studio/libobs`
- `OBS_LIB_DIR`: `/Applications/OBS.app/Contents/Frameworks`
- `OBS_CONFIG_DIR`: falls back to `obs-plugin/obsconfig` if a build config is unavailable

If OBS is installed elsewhere, pass custom paths:

```bash
cmake -S obs-plugin -B obs-plugin/build \\
  -DOBS_INCLUDE_DIR="/path/to/obs-studio/libobs" \\
  -DOBS_LIB_DIR="/path/to/OBS.app/Contents/Frameworks"
cmake --build obs-plugin/build
```

## Install (macOS)
The build outputs a `.plugin` bundle. Copy it into OBS plugins:

```bash
cp -R obs-plugin/build/what_overlay_plugin.plugin \\
  "$HOME/Library/Application Support/obs-studio/plugins/"
```

## Build (source SDK, optional)
If you want to build against OBS source + libobs, point to your build outputs:

```bash
cmake -S obs-plugin -B obs-plugin/build
cmake --build obs-plugin/build
```

## Implementation Notes
- `overlay_client` should handle SSE from `http://127.0.0.1:8790/events`.
- `overlay_source` should translate OBS properties into `OverlayConfig`.
- `plugin.cpp` should register a source named `What Captions`.
- Rendering should use `libobs` text rendering helpers to avoid external deps.

## Next Steps
1. Wire OBS SDK dependency (obs-studio headers + libobs).
2. Implement `overlay_client` (SSE/WebSocket client).
3. Bind `overlay_source` to OBS source API and expose properties.
4. Render text with `gs`/`libobs` graphics utilities.

## Custom Qt Panel
- An optional dockable Tools panel (Qt) offers compact grouped controls that are not achievable with source-properties layout alone.

## Milestone 1 Scaffold
- A frontend scaffold is now available (build-gated):
  - CMake option: `WHAT_OVERLAY_ENABLE_FRONTEND_PANEL=ON` (default ON).
  - Requires `obs-frontend-api.h` include path (`OBS_FRONTEND_API_INCLUDE_DIR`).
  - Registers a Tools menu item: `What Captions Panel (Scaffold)`.
- Current scaffold behavior:
  - Menu entry toggles a dock widget stub from Tools menu.
  - Stub currently contains a delay control and apply button.

## Milestone 2 Shared State
- Added shared runtime state module:
  - `include/what_overlay/overlay_state.h`
  - `src/overlay_state.cpp`
- Source and panel now exchange config via a versioned shared snapshot:
  - Source writes to shared state on source-properties updates.
  - Panel writes delay updates to shared state.
  - Source polls shared state in `video_tick` and applies changes live.
- This is plumbing only; dense grouped controls are still Milestone 3.

## Milestone 3 Panel Scaffold
- The Qt dock now exposes compact grouped controls and Apply/Revert:
  - Max Seg + Max Chars
  - Font Size + Delay
  - Text Color + Background Color
  - Width + Height
  - Align + Font
  - Animation mode
- Apply writes through shared state to the active source.
- Revert reloads values from shared/source state.

## Milestone 4 Compatibility Pass
- Aligned panel/source defaults to reduce startup drift:
  - Default background now transparent (`#00000000`, 0% opacity).
  - Default delay is `0s`.
- Ensured panel/source parity for test-stream toggle behavior and shared-state propagation.
- Kept source-properties workflow functional as fallback.
- Added/retained build-gated frontend path so panel-off builds remain supported.
- Live Output defaults to plain mirror mode; segment color view is opt-in via:
  - `Color Segments (Experimental)` in the panel.

## Measured Layout Scaffold (Step 1-2)
- Added modular scaffolding for the measured-layout path:
  - `src/layout/font_metrics.cpp`: font measurement adapter with LRU cache.
  - `src/layout/line_layout.cpp`: line layout engine API (`LayoutRequest -> LayoutResult`).
  - Headers in `include/what_overlay/layout/`.
- This scaffold is linked into the plugin build but not yet switched into live rendering.

## Measured Layout Toggle (Step 3 WIP)
- Source property `Layout Engine` now exists with:
  - `legacy` (default)
  - `measured_v1` (experimental path using `layout/` modules)
- `measured_v1` currently covers measured wrapping/alignment preparation while preserving existing rendering architecture.

### Milestone 4 Regression Checklist
- Open/close panel repeatedly from Tools menu.
- Toggle Test Stream from panel and verify API GUI follows.
- Change Delay from panel and verify readback updates.
- Verify transparent background default on fresh source add.
- Verify source-properties edits still apply when panel is closed.

## Project Known Issues
- See `KNOWN_ISSUES.md` for currently tracked issues and status.

This skeleton is intentionally lean and platform-agnostic for now.
