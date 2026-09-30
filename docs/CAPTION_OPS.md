# Caption Ops Envelope

`what` now emits semantic line operations inside each `segment` event under `caption_ops`.

## Envelope

```json
{
  "type": "caption_ops",
  "session_id": "default",
  "seq": 1,
  "ts_ms": 1739940000000,
  "ops": []
}
```

## Ops

- `line_open`
  - fields: `line_id`, `after_line_id`, `reason`, `segment_id`, `segment_start_ms`, `segment_end_ms`
  - `reason` values:
    - `manual`: first line
    - `gap`: break chosen by silence gap
    - `width`: break chosen by line width
- `line_append`
  - fields: `line_id`, `text`, `segment_id`, `overflow_allowed`
- `line_close`
  - fields: `line_id`
- `line_evict`
  - fields: `line_id`, `reason` (`max_lines`)
- `warning`
  - fields: `line_id`, `segment_id`, `code`, `message`
  - current code: `line_overflow` (single token exceeds configured line width)

## Current Rules

- Gap priority is higher than width priority.
- If both could apply on a boundary, `gap` is emitted as the break reason.
- User edits can intentionally overflow visual width in consumers.
- Machine append operations preserve continuity by appending in-place.

## Current Limits

- Width is currently character-count based, not glyph metrics.
- Machine in-place correction ops (`segment_replace_range`) are not emitted yet.

