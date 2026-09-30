# What Caption Box

The plugin registers **What Caption Box**, an OBS source that owns a private Browser
source pointed at the same `/caption-box` page used by the preview and manual URL route.
The legacy **What Captions** native source remains available.

## Build and install on macOS

With the OBS SDK paths described in [README.md](README.md):

```sh
cmake -S obs-plugin -B obs-plugin/build
cmake --build obs-plugin/build -j 4
```

If the compiler reports an unsupported architecture in the default SDK's `libSystem.tbd`,
choose an SDK belonging to the selected Xcode toolchain. This machine's verified command is:

```sh
cmake -S obs-plugin -B obs-plugin/build \
  -DCMAKE_OSX_SYSROOT=/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX26.5.sdk
cmake --build obs-plugin/build -j 4
```

Quit OBS, then install the built bundle and reopen OBS:

```sh
mkdir -p "$HOME/Library/Application Support/obs-studio/plugins"
cp -R obs-plugin/build/what_overlay_plugin.plugin "$HOME/Library/Application Support/obs-studio/plugins/"
```

## Use

1. Start `what` and open `http://127.0.0.1:8790/caption-box-settings` (use the app's actual
   port if different). Choose Mic/Desktop, font size, and padding; copy the URL.
2. In OBS, add a **new What Caption Box** source. Paste the URL and set the starting Width
   and Height. Existing ordinary Browser sources do not automatically become wrappers.
3. Leave **Reflow after dragging resize handles** enabled. Drag a handle; hold Shift for
   independent width/height changes. After approximately 200 ms without a scale change,
   the plugin converts the displayed size into browser viewport dimensions and resets
   the scene-item scale to 1. The URL, font size, and padding remain unchanged.
4. In OBS’s Add dialog, choose **Create new**, not **Add Existing**, for another layout. Both
   sources can consume the same caption URL while retaining independent geometry.

The drag conversion is limited to one direct scene placement with positive scale, no
crop, no bounding-box transform, and no lock. Grouped or multiply referenced sources are
left alone. Scaling an enclosing group or nested scene still scales the whole composition.
Rotation and position of an eligible item are preserved. Dimensions are limited to
80–4096 px wide and 60–4096 px high. Explicit source Width/Height settings always work.

A previously saved scale is treated as a baseline on load, not an instruction to resize.
The helper watches new gestures. During a gesture OBS may temporarily scale the texture;
conversion happens after the short pause. Width/height-only updates use obs-browser's
viewport resize path rather than reloading the page, preserving its caption history.

Disable the checkbox if you want ordinary source scaling. The manual URL route continues
to support explicit Browser source Width/Height edits without this plugin.

## Validation status

The macOS plugin builds. The pure resize policy and an adapter test using real libobs
with a browser stand-in pass. The adapter covers dimension persistence, scale reset,
shared-reference/crop/bounds/lock exclusions, the off switch, and child lifecycle.
The owner confirmed live drag-to-reflow, including Shift aspect changes, in the main scene
and successful reflow in Aitum Vertical using a separate new source. Scene reload
persistence and sustained overflow still need the remaining checks in [MACOS_SMOKE_TEST.md](../docs/MACOS_SMOKE_TEST.md).
