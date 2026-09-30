# Future Work

> Status update, 2026-09-17: The authoritative v0.1/v0.2 scope is now [docs/PROJECT_BRIEF.md](docs/PROJECT_BRIEF.md), including transcript replay in v0.1 and correction-driven local improvement in v0.2. The ideas below are a backlog, not additional release requirements.

## Multilingual Captioning and Layout

`what` currently uses mostly Latin-script assumptions for wrapping and segment display. To support more languages robustly, prioritize:

### Panel UX follow-up
- Replace current font-size slider + spinbox with a "scrubbable value field":
  - Click to edit text directly.
  - Click-drag horizontally to scrub value while cursor stays anchored.
  - Keep fine-grain manual entry and coarse scrub stepping.
  - `SCRUB_HOLD_MODE`: when pointer is held near-still for ~1.5s while dragging, switch to high-precision scrub (`0.05` steps).

### Box Label Styling Follow-up
- Add per-box label text customization independent from body caption text.
  - Each box (`Mic`, `Desktop`) should have its own label text value (not hardcoded to source name).
  - Label typography and color should be independently styleable per box (font family, size, weight, color, optional outline).
  - Label style controls should not mutate body text style controls.
  - Keep `box_label` as canonical label metadata field, and extend settings with label-style fields per box.

1. Unicode-aware segmentation:
- Replace space-based tokenization with grapheme/word boundary rules (UAX #29).
- Treat combining marks, emoji ZWJ sequences, and Indic scripts as atomic grapheme clusters.

2. Script-specific line breaking:
- Use Unicode line-breaking rules (UAX #14) instead of character-width heuristics.
- Add language/script-specific policies for CJK (no spaces), Thai/Khmer (dictionary break), and RTL scripts.

3. Bidirectional text and shaping:
- Ensure rendering path supports BiDi reordering (Arabic/Hebrew mixed with Latin).
- Validate shaping with complex-script fonts (Arabic, Devanagari, Thai).

4. Font fallback strategy:
- Implement fallback chains per platform for missing glyphs.
- Surface missing-glyph diagnostics in logs/UI for easier user debugging.

5. Locale-aware punctuation/case:
- Avoid global uppercase transforms for languages where casing is invalid or lossy.
- Add per-language normalization and punctuation spacing profiles.

6. Width measurement accuracy:
- Replace heuristic width estimates with glyph measurement from the active font/render backend.
- Cache measured token widths for performance under live updates.

7. Test corpus expansion:
- Add replay fixtures for English, CJK, Arabic/Hebrew (RTL), Indic scripts, emoji-heavy speech, and code-switching.
- Add visual regression snapshots for wrap/overflow/alignment behavior.

8. Editing model by language:
- Keep user edits anchored to grapheme ranges (not bytes/chars) to avoid split-cluster corruption.
- Preserve segment identity through language-aware reflow.

9. OCR/Overlay readability profiles:
- Add presets per script (line height, stroke/shadow, preferred fonts, max chars/line).
- Include low-resolution streaming presets for legibility on mobile viewers.

10. Telemetry for quality loops:
- Track per-language correction rates and wrap-overflow incidents.
- Use this to prioritize tokenizer/layout improvements and defaults.
