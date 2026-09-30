# macOS app smoke test

Run from the existing development checkout. There is no full `what` application-bundling
script in the inspected repository. `native/what-coreaudio-tap/build.sh` builds only the
`WhatCoreAudioTap.app` audio helper; it is not the desktop GUI.

Launch the controller and Electron GUI together:

```bash
cd /path/to/what
_venv/bin/python -m what gui
```

The current checkout already has the virtual environment, Electron dependencies, and a
rebuilt WhisperKit worker. The launcher reuses a controller already listening on port 8780.
The GUI uses the configured/saved model; the earlier standalone model smoke used `base`.

1. In the GUI, enable Mic and leave Desktop off. Open Settings, choose File as the mic
   input mode, and select a local speech WAV you have permission to use. Keep Profile `captions` and Delay `0`.
2. Open `http://127.0.0.1:8790/overlay?box=mic` in a browser. Click Start in the GUI.
   Text should appear both in the transcript and browser overlay. The overlay keeps three
   recent events; the transcript retains session history independently.
3. Click Stop: browser captions should clear. Start again: old captions should not return.
4. Repeat with Delay `2`: transcript updates should precede browser captions by about two
   seconds. Stop before a delayed update arrives: it should not reappear afterward.
5. For a live capture check, switch the mic input back to Mic and speak. Then enable Desktop
   as well, complete its permission/setup prompts if shown, and play speech on the Mac.
   Check the separate desktop overlay at `http://127.0.0.1:8790/overlay?box=desktop`.
6. In OBS, add a Browser source with the mic or desktop URL, initially 640 × 240. Confirm
   live text appears and clears on Stop. This exercises the browser output; the native
   plugin is not needed for this check.

The default overlay endpoint uses port 8790; if occupied, check the launch terminal for the
actual overlay-server port. Capture any failures from the GUI Debug section and terminal.

Word-click replay and persistent scrollback are implemented in the default GUI. The
browser integration checks below cover reflow and source persistence.


## Browser caption-box prototype

After launching the app, open `http://127.0.0.1:8790/caption-box-settings` (use the actual
server port from the terminal if different).

1. Select Sample text. Drag the preview's bottom-right handle narrower/wider: words should
   rewrap with unchanged font size and padding. Change Height: only complete newest lines
   should remain. Increase Font size separately to check that dimensions do not scale.
2. Select Live captions and the desired source, then start transcription. Existing completed
   lines should remain stable as words arrive; Stop should clear output.
3. Copy URL and add it as an OBS Browser source. Set OBS Width and Height to the preview values.
   Compare its line breaks with the preview at the same dimensions. Change source Width
   directly in OBS properties: text should reflow without font scaling.
4. Check a very narrow box and very short box. An oversized word should clip without changing
   font size; less than one usable line should show no body text.

OBS canvas drag handles still scale the source; the plugin/synchronizer that converts this
into reflow is a later step. The existing `/overlay` route is unchanged.


### Frozen-line regression check

After restarting `what`, refresh each `/caption-box` OBS Browser source. Use a long continuous
sample that produces more than three caption events. A full line should keep exactly the same
words until it scrolls out; event-window rollover must not erase its beginning or repack it.
When another line fills, the display should scroll upward smoothly. Repeat a short phrase
several times: each occurrence should appear once. Stop/Start should clear the old session.
Explicit width/font changes may reflow, and reduced-motion mode disables the scroll animation.

## OBS wrapper: drag-to-reflow

Build/install instructions: [What Caption Box](../obs-plugin/BROWSER_CAPTION_BOX.md).
Quit OBS before copying the rebuilt plugin; restart `what` to load the latest renderer.
This check uses a **new What Caption Box source**, not an existing ordinary Browser source.

1. Copy the mic URL from `/caption-box-settings` with font size 32, padding 12, width 640,
   and height 240. Add What Caption Box in OBS with those values. Confirm live captions.
2. Hold Shift and drag a side/corner handle to narrow the box. Pause/release: after about
   200 ms, source Width should match the new size and Edit Transform scale should be 1.
   Words should rewrap; glyph size and padding should return to their original size.
3. Change only height. Confirm whole oldest lines leave as capacity shrinks, and captions
   continue smoothly without resetting to only the publisher's latest three chunks.
4. Repeat narrowing/widening during continuous speech. After each pause, observe no repeated
   resizing, oscillation, lost stream, or changes to previously frozen lines until reflow.
5. Move and rotate the source. Position/rotation should remain intact during subsequent
   resizes. Disable drag reflow: dragging should then behave as ordinary OBS scaling.
6. Add a second **new** source using the same URL. Resize it and confirm the first retains
   its size. Repeat on another canvas if available. A shared reference, grouped/cropped/
   bounded/locked source should not be automatically converted; explicit dimensions work.
7. Restart OBS. Confirm the resized Width/Height and scale 1 persist, and captions resume
   when `what` publishes. Opening a scene with an existing non-unit scale must not trigger
   a resize by itself.

Automated tests cover resize decisions and the libobs settings/scene adapter with a fake
browser. They do not establish the CEF rendering or mouse-gesture results above.

### Vertical follow-up

Owner confirmed dragging and Shift aspect changes in the main scene and successful reflow
in Aitum Vertical with a new What Caption Box source. The reported vertical stretching
came from **Add Existing**, which creates a shared reference. For independent geometry,
choose **Create new** for each layout and paste the same caption URL. Shared references
intentionally retain ordinary scaling because their browser viewport belongs to one source.

## Runtime audio-device switching (v0.1 acceptance)

Restart the development app to load the main-process changes. Keep the same transcription
session running throughout these checks; do not use Stop/Start between device changes.

1. Enable Mic and Desktop, speak, then choose another **Mic device** in Settings. Confirm
   the selected input produces new speech and desktop captions continue. Existing transcript
   history and earlier word replay must remain available. Each reopened mic capture gets a
   distinct client/recording identity within the existing service session.
2. Alternate between two inputs at least 20 times, including quick A → B → A selections.
   The last choice must win with only one mic capture client. Retry the current input using
   the refresh button; it now refreshes the list and reopens active mic capture.
3. With **System default input** selected, change macOS's default input repeatedly. Allow
   up to three seconds for detection. Repeat with a named device selected: unrelated default
   input changes should not replace that chosen device.
4. Unplug the selected input, then reconnect or select another. Failure should be visible;
   the service and desktop lane must remain running. A subsequent selection must recover.
5. While replaying an earlier transcript word, change **Transcript playback output** between
   headphones, speakers, and System default output. Confirm the same passage continues at
   the same playback position. Change the OS default output while using the default choice.
6. Unplug the selected playback output. Replay should stop with an explanation rather than
   silently route to an unintended device. Choose an available output and replay again.
7. Press Stop during an input switch. It must stay stopped; a late switch must not reopen
   capture. Also rapidly request two different replay passages during output changes: an
   older load/error must not stop or start the newer passage.
8. Confirm desktop replay suppression still applies on every playback output. Acoustic
   pickup through a live mic remains possible when using speakers.

The queue/routing/process tests run without audio hardware and provide cross-platform
regressions. macOS device polling and actual FFmpeg/Chromium/driver hot-plug behavior require
these live checks. Windows/Linux input enumeration and routing remain experimental.
