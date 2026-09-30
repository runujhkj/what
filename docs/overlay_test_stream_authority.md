# Overlay Test-Stream Authority

## Purpose

Define a single modular authority for test-stream lane constraints so that bridge/IPC/runtime all apply the same normalization and merge rules.

## New/Updated Module Responsibilities

- `gui/lib/overlay_layout_budget_authority.js`
  - pure geometry/font/limits derivation
  - computes:
    - `contentWidthPx`
    - `maxVisibleLines`
    - `maxLineChars` (+ derivation metadata)
  - intentionally does not perform wrapping, freezing, or segment eviction

- `gui/lib/overlay_constraints_authority.js`
  - owns box-key normalization (`normalizeBoxKey`)
  - owns outbound payload shaping for renderer -> main (`buildSetTestStreamPayload`, `buildSetTestStreamPayloads`)
  - owns bridge constraint patch extraction (`buildConstraintPatch`)
  - owns runtime/fallback constraint merge (`mergeRuntimeLaneConstraint`)

- `gui/lib/main_test_stream_bridge.js`
  - no longer parses numeric constraint fields directly
  - delegates constraint patch build + box normalization to `overlay_constraints_authority`
  - remains responsible for call ordering:
    1. `setConstraints(...)` when a patch exists
    2. `setEnabled(...)`

- `gui/lib/overlay_ipc_handlers.js`
  - no longer owns box normalization + geometry merge rules
  - delegates these decisions to `overlay_constraints_authority`
  - remains responsible for:
    - reading fallback config from current overlay payload
    - logging/debug capture
    - dispatching `setOverlayTestStreamEnabled(...)`

## Decision Ownership (Single-Owner Rule)

- `overlay_constraints_authority`: constraint normalization + merge policy
- `overlay_layout_budget_authority`: budget derivation only (no content logic)
- `main_test_stream_bridge`: toggle sequencing (`constraints -> enabled`)
- `main_overlay_test_stream_runtime` + `test_stream_lane_policy`: lane composition and rollover behavior
- `overlay_payload_writer`: payload envelope contract only

## Regression Coverage

- `gui/tests/overlay_constraints_authority.test.js`
  - payload shaping
  - patch extraction from partial/empty input
  - runtime merge behavior with stale debug geometry fields
- `gui/tests/overlay_layout_budget_authority.test.js`
  - explicit-vs-derived max-line-char behavior
  - geometry/font sensitivity of char budget derivation

- Existing integration tests continue to validate call-site behavior:
  - `gui/tests/main_test_stream_bridge.test.js`
  - `gui/tests/overlay_ipc_handlers.test.js`

## Observability

- Per-lane authority winner metadata is now attached as `authorityTrace` on runtime constraints.
- GUI tick telemetry includes compact lane authority traces:
  - `mic_auth='{pref=... L=... C=... S=... W=... P=... F=... M=...}'`
  - `desk_auth='{pref=... L=... C=... S=... W=... P=... F=... M=...}'`
- Winner codes:
  - `incoming`: value came from the immediate payload for that lane
  - `fallback`: value came from box config fallback (stale/missing raw geometry case)
  - `derived`: value was recomputed (not directly trusted from payload)
