# Project brief

Agreed direction, 2026-09-17. This document is authoritative for product scope.
Known gaps are listed in [KNOWN_ISSUES.md](../KNOWN_ISSUES.md).
Targets below are requirements, not claims that the current app meets them.

## Purpose

`what` is a local live-transcription workspace that produces stream captions,
lets users revisit speech through an editable, audio-linked transcript, and uses
corrections to improve recognition of familiar speech sources over time.

The workflow is: listen → transcribe → revisit → correct → improve.
Other applications can consume its transcript stream.

## Responsibilities

- Capture microphone and desktop audio and transcribe locally.
- Keep source-specific recordings and transcripts with stable identities and timing.
- Support transcript history, audio replay, and corrections while capture continues.
- Publish readable captions with controllable delay, typography, and geometry.
- Preserve correction provenance for local improvement in v0.2.

## v0.1 acceptance requirements

### Capture and lifecycle

- Start, stop, and restart microphone and desktop capture independently and together.
- Surface actionable capture/model/connection failures; avoid silent stalls.
- Keep recording time, emitted timestamps, and source identity aligned across reconnects.
- Expose recording state and storage controls; replay must explain unavailable audio.
- Document tested OS, engine, and installation combinations. Platform support is earned
  through validation; existing setup scripts alone do not establish support.

### Runtime audio-device switching

- Change the active input repeatedly during a session without restarting the service or
  losing transcript history, existing recordings, or the other capture source.
- Change transcript playback output repeatedly, including during replay, preserving the
  playback position and desktop-recapture suppression. Offer a system-default output choice.
- Rapid changes must settle on the latest selection; Stop must cancel pending capture work.
- Device removal and failed switches must be visible and recoverable by selecting or retrying
  an available device. Saved unavailable devices must not silently become another device.
- Preserve recording identities/timestamps across capture reopenings. Verify repeated switches,
  hot-plug recovery, default-device changes, and stop/switch races with portable regression
  tests plus live checks on each platform claimed as supported.

### Transcript workspace

- Retain session history independently of the short caption display window.
- Allow scrolling back without new speech forcing a jump to the bottom; provide Return to live.
- Normal interaction selects/edits text. A platform-appropriate modifier-click on a word
  seeks to that word's audio timestamp in the correct source recording.
- Provide stop playback and a segment-level fallback when word timing is unavailable.
- Keep historical review separate from live caption publication. Replay must not be
  inadvertently captured as fresh desktop speech; deliberate reinjection is deferred.
- Preserve original recognition and timing when editing. Corrected character offsets
  are not new word timestamps; use passage bounds for approximate seeking when needed.
- Save corrections with session/client/source identity, original and corrected text,
  segment identity, audio interval, and recognition context. Missing audio/timing must
  be explicit rather than producing an apparently usable learning pair.

### Caption output and OBS

Use one browser renderer through two supported entry points:

1. A copyable local URL for a manually added OBS Browser source.
2. An OBS plugin that creates/configures that browser source and adds integrated controls.

The plugin is an integration layer, not a second text-layout implementation. It should
make dragging change the browser viewport dimensions without scaling the font. The
manual URL route can use explicit source width/height settings without that helper.

`what` owns transcript identity, delay, corrections, and history policy. Browser rendering
owns font measurement and wrapping. Caption box dimensions and padding are independent
of font size. Preview and OBS should consume the same rendering implementation.

Completed lines stay stable as new speech arrives. Intentional resizing permits visible
text to reflow. The prototype must settle correction and overflow behavior explicitly;
CSS wrapping alone does not implement stable rolling captions. Each independent layout
needs its own geometry configuration, even when it consumes the same transcript stream.

Keep the existing native renderer available during validation of the replacement.
Do not remove it until the browser path passes the agreed acceptance checks.

## v0.2: local improvement

Use corrections to reduce recurring errors for familiar speech sources. Capture channels
(`mic`, `desktop`) and familiar sources (a person or recurring program) are separate
concepts. Selectable source profiles can precede automatic speaker recognition.

Success means fewer recurring errors on held-out recordings from the relevant source,
without unacceptable regressions on other speech. Record the engine/model and adaptation
version so improvements are reproducible and reversible. Separate training examples from
evaluation examples. Export/import alone is not learning.

Evaluate vocabulary/context hints and correction-derived adaptation before committing
to model fine-tuning. The mechanism remains open; demonstrated improvement is the target.

## Deferred work

- Automatic speaker recognition/diarization as a prerequisite for source profiles.
- Model fine-tuning as a mandatory implementation choice.
- Deliberately feeding replay into live transcription.
- Advanced in-preview authoring beyond useful style and resize controls.

## Publication and release

A public early repository and a polished v0.1 installation are separate milestones.
Publication needs accurate status, an explicit license decision, reviewed tracked data,
and reproducible contributor setup. v0.1 additionally needs the workflow acceptance
checks above, clean-install verification, and sustained live capture/OBS validation.

Historical implementation plans are context, not additional release requirements.
