# Diarization Notes (Unfinished)

## Current State
- No automatic speaker diarization is implemented.
- GUI supports manual `speaker_id` selection and stores it with corrections.
- Corrections logs include `speaker_id`, `speaker_is_me`, and `input_source_id`.

## Open Questions / Incomplete Areas
- Speaker identification in mixed audio (single stream) is not solved.
- How to map corrections from multiple speakers when audio is merged.
- Whether to add true diarization vs. keep manual speaker tagging.
- How to reconcile speaker IDs across machines (export/import mapping).

## Planned Foundations (Not Implemented Yet)
- Speaker ID attached to segment events (service → client → GUI).
- Speaker selector per transcript session (prompt if default disabled).
- Export/import mapping of `me` across instances.
- Per-speaker correction subsets for training.

## Recommended Next Steps (If Pursued)
1. Add `speaker_id` to segment events and store with segments.
2. Define an export/import mapping format for speaker IDs.
3. Add a per-session “active speaker” selector (for mixed streams).
4. Consider true diarization only after above plumbing is stable.
