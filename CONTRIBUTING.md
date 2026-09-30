# Contributing

Start with [README.md](README.md) and [the project brief](docs/PROJECT_BRIEF.md).
The Python service, Electron GUI, and optional OBS plugin share this checkout. Run commands
from the repository root; a wheel alone does not include the GUI or native workers.

Use Python 3.12 and a local `_venv` for the macOS path. The README lists Python, Node, FFmpeg,
and Swift prerequisites. `npm ci` uses the tracked GUI lockfile; Swift uses Package.resolved.
Python dependencies currently have broad version constraints, so a fully pinned,
cross-platform clean installation remains a release task.

```sh
_venv/bin/python -m pip install pytest
_venv/bin/python -m what --help
npm --prefix gui test
_venv/bin/python -m pytest -q
```

The Python suite includes host-dependent audio/network/model checks and optional skips.
Report the exact command, OS, engine, and failures rather than treating every pass as a
live capture test. Use [MACOS_SMOKE_TEST.md](docs/MACOS_SMOKE_TEST.md) for live checks.
For the optional plugin, build as documented in [its guide](obs-plugin/BROWSER_CAPTION_BOX.md),
then run `ctest --test-dir obs-plugin/build --output-on-failure`. The latest baseline has
one legacy `what_overlay_test_fit_decider` failure (a known issue in the native renderer).

Keep recordings, correction data, `.env` files, model caches, and builds out of commits.
Use synthetic fixtures for regressions. Do not paste credential values into issues.
For reports, include reproduction steps and redacted diagnostics, not real transcripts.

Changes should include focused checks for the behavior they affect. Mark proposed behavior
as proposed in documentation. Contributions to project-authored code use GPL-3.0-or-later;
retain existing third-party notices and identify the origin/license of imported code.
