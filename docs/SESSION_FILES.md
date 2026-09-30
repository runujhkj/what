# Session files

Every run ("session") of `what` is stored in its own folder, `<logs>/<session_id>/`, where
`<session_id>` looks like `2026-09-18_007_T103758` (date, index for the day, start time).
The implementation is `what/session_files.py` (Python) and `gui/lib/session_loader.js`,
`gui/lib/session_workspace.js` (GUI).

## Folder contents

| File | Written by | Contents |
| --- | --- | --- |
| `<client_id>.jsonl` | service | One JSON segment event per line, for one client connection. `client_id` starts with `mic-` or `desktop-`; a mic device switch starts a new client, so a session can have several mic files. |
| `<client_id>.wav` | service | That client's recording (16 kHz mono PCM). Appended if the same client reconnects. |
| `corrections.jsonl` | GUI | Review edits (`what.correction.v1`), one line per saved edit. |
| `process.log` | controller | Controller log for the session. |
| `transcript.txt` | service, controller, GUI | All sources in time order (below). |
| `<session_id>.what` | controller, GUI | The session in one file (below). |

### Timing

Segment `abs_start`/`abs_end` (and word times) are offsets in seconds into the client's
`.wav`. Each event also carries `stream_started_at`: the wall-clock time (Unix seconds) of
sample 0 of that recording, so `stream_started_at + abs_start` is when the speech happened.
That is what orders segments from different sources against each other. Logs written before
`stream_started_at` existed fall back to `wall_time - chunk_end` (the event is written just
after its chunk ends), which is off by the decode delay.

## transcript.txt

```
What transcript: session 2026-09-18_007_T103758
Sources: Desktop (desktop-bbbb2222); Mic (mic-aaaa1111)
Recorded: 2026-09-18 10:37:59 to 10:38:04 (local time)
Blocks marked (edited) include corrections made in review.

[10:37:59 - 10:38:01] Mic (edited)
    Hello there. How are you doing?

[10:38:03 - 10:38:04] Desktop
    I'm fine, thanks.
```

Consecutive segments from the same source less than 4 seconds apart are shown as one block.
The latest correction of each segment replaces its text; a segment corrected to nothing is
left out. Times are local; the date is added to every time when a session spans midnight.

It is refreshed when a source disconnects, when the session stops, after review edits
(batched, about 2 s), and when a `.what` file is opened.

## .what files

A `.what` file is a zip archive:

- `manifest.json`: `{"format": "what.session", "version": 1, "session_id", "created_at",
  "app_version", "sources": [...], "corrections", "transcript", "process_log"}` (file names,
  or `null` when absent). Each source is `{"client_id", "source", "transcript", "recording",
  "recording_file", "recording_codec", "recording_bytes"}` plus `"sample_rate"` and
  `"channels"` for FLAC: `recording` is the `.wav` name in the session folder,
  `recording_file` the archive member holding it.
- The files listed in the manifest, flat (no folders).

Recordings are stored as FLAC (`recording_codec: "flac"`), which is lossless: opening the
file decodes them back to byte-identical WAVs (checked against `recording_bytes`), so replay
positions and appending on Continue are unaffected. Speech with pauses typically takes half
or less of the WAV's size. Packing and opening FLAC need FFmpeg (bundled with the Windows
and macOS apps, required on Linux anyway); without it a `.what` file stores the WAV as is
(`recording_codec: "pcm"`), and a file with FLAC recordings cannot be opened.

It is written when the controller stops a session (Stop, or quitting the app) and when edits
are saved in review. Opening one (File → Open Session, or `what session unpack`) restores
its files into `<logs>/<session_id>/`:

- A file that already exists there and is at least as large is kept: the logs are
  append-only, so the local copy is the same session with possibly more recorded since.
- A folder that holds a *different* session under the same id is refused.

Starting capture with a reopened session loaded continues it: the controller is started with
`resume_session_id`, and the new client connections add their own `.jsonl`/`.wav` files to
the same folder.

## Command line

```sh
what session transcript logs/<session_id>          # write transcript.txt
what session pack logs/<session_id> [--copy-to x.what]   # write transcript.txt and the .what file
what session unpack file.what [--logs-dir DIR]     # restore into DIR/<session_id>/
```

`--json` prints a one-line JSON result (used by the GUI). The default logs folder is
`WHAT_JSONL_DIR`, else `./logs`.
