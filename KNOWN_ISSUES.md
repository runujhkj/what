# Known Issues

## OBS Plugin

- Delay apply latency can occasionally spike on repeated quick changes.
  - Status: non-blocking and eventually consistent.
  - Scope: `Tools -> What Captions Panel` delay changes.

- Font-size slider precision drops in very small panel widths.
  - Status: slider can become harder to hit exact `0.05` increments when compact.
  - Scope: `Tools -> What Captions Panel` typography controls.
  - Follow-up keyword: `SCRUB_HOLD_MODE` (see `FUTURE_WORK.md`).

- Qt dock panel values are runtime-only in the current milestone.
  - Status: values are not persisted as a panel-specific preset yet.
  - Scope: panel controls repopulate from current shared/source state.

- Live Output mirror is the authoritative debug mode; segment colorization is experimental.
  - Status: `Color Segments (Experimental)` can still show edge-case span drift during rapid rollover.
  - Scope: panel-only `Live Output`; does not affect OBS source rendering.

- Panel and OBS source bounds are close but not guaranteed pixel-identical.
  - Status: two different text renderers/layout engines (Qt vs OBS text source) can diverge at edges.
  - Scope: visual comparison between panel `Live Output` and in-scene `What Captions` source.

- Live Output minimap is disabled.
  - Status: non-critical; disabled because current viewport math can report "full area" in cases where users expect a sub-viewport indicator.
  - Scope: panel-only minimap widget (does not affect source rendering or transcription).
  - Future scoped fix: reintroduce as a fixed-size viewport model where panel preview intentionally views only a sub-rectangle of source bounds, so minimap always has meaningful total-vs-view data.

- Panel section expand/collapse can visibly twitch.
  - Status: non-critical visual issue during section open/close height transitions.
  - Scope: `Tools -> What Captions Panel` sectioned/collapsible shell.

## Transcript workspace (default GUI)

Accepted limitations for v0.1.

- Earlier sessions are reopened only through **File → Open Session** with their `.what`
  file. A session whose run ended without the controller stopping it (a crash or a killed
  process) has no `.what` file yet; `what session pack logs/<session_id>` writes one.
- A `.what` file stores the recordings uncompressed, so it takes about as much disk space as
  the session folder (about 115 MB per source per hour).
- Opening a `.what` file by double-clicking it is not set up yet; use File → Open Session.
- Replay through speakers can still be picked up by a live microphone. Desktop capture is
  silenced during replay, but the mic is not; use headphones or stop the mic source.
- A correction covers one segment. An edit spanning two segments is saved as two corrections,
  and edits do not change captions that were already published.
- `what/corrections.py` export/import still reads only the older `corrections/` folder, not
  the per-session `logs/<session_id>/corrections.jsonl` the default GUI writes.
- macOS may move the system output device when capture starts (observed once). Nothing in
  `what` sets the output device; the GUI now reports such a change with its cause step.

## GUI Stub

- Electron GUI can intermittently flash a white frame during restart/reload.
  - Status: startup retry was added for port conflicts; occasional white-frame remains.
  - Scope: `what gui` startup/restart path.
