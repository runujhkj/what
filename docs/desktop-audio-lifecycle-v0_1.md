# Desktop Audio Lifecycle v0.1

## Scope

This document defines the v0.1 runtime behavior for desktop capture in OBS/controller integration.

## Rules

1. `what-desktop` is the required desktop routing target.
2. BlackHole remains the fixed loopback component.
3. A user-selected physical output can be paired with BlackHole when rebuilding routing.
4. Desktop stream start hard-fails when `what-desktop` cannot be made available.
5. No opportunistic fallback to arbitrary non-`what-desktop` targets in v0.1 policy.

## Controller APIs (modular)

Implemented in `what/controller/routes_desktop_audio.py` with helper runtime in
`what/controller/desktop_audio_output_runtime.py`.

- `GET /control/desktop-audio/outputs`
  - Returns output candidates derived from `bin/what-coreaudio-aggregate list-outputs`.
  - Includes `kind` (`physical`, `loopback`, `aggregate`) and `selectable`.
  - Returns persisted `selected_output` from routing receipt.

- `POST /control/desktop-audio/output/select`
  - Persists the user-selected physical output name into routing receipt (`selected_output`).

- `POST /control/desktop-audio/rebuild`
  - Removes managed routing and re-applies routing.
  - Used to rebuild/update `what-desktop` with current selected output + loopback.

## Helper behavior

`bin/what-coreaudio-routing` now reads `selected_output` from the routing receipt and prefers it as
the listening physical output during aggregate creation in `ensure`.

## Remaining panel integration work

The OBS panel start flow still needs to call the new APIs in this order for desktop-start:

1. Ensure/install desktop audio components if missing.
2. Rebuild routing (`/control/desktop-audio/rebuild`).
3. Start stream (`/control/stream/start`) and validate effective source flags.

This keeps desktop start deterministic and aligned with v0.1 policy.
