<p align="center"><img src="docs/images/logo.png" alt="what." width="256"></p>

# what

Local live transcription, OBS captions, and an editable transcript linked to recorded audio.
Listen → transcribe → revisit → correct. Using corrections to improve recognition is a
v0.2 goal, not an implemented learning feature.

## The v0.1 target

v0.1 is one application with the same feature set on macOS, Linux, and Windows:

- Local live transcription of microphone and desktop audio, independently or together.
- A retained, scrollable transcript with **Return to live**.
- Modifier-click a word to replay its recording; double-click a segment to correct it.
- Browser captions for OBS, as a plain Browser source or the What Caption Box plugin.
- A readable all-source transcript (`transcript.txt`) and a single session file
  (`<session_id>.what`) for every run; **File → Open Session** reopens one to review, edit,
  replay, or continue it.
- Everything local: recordings, transcripts, and corrections stay on your machine
  (`logs/<session_id>/` in a source checkout; in the apps, `%APPDATA%\What\logs` on Windows,
  `~/Library/Application Support/What/logs` on macOS, `~/.config/What/logs` on Linux).

The workflow and UI are identical across platforms. What differs underneath is the speech
engine and the desktop-audio backend, chosen automatically per platform (see the table
below). No cloud services and no account are involved.

## Download

Get the file for your platform from the [latest release](../../releases/latest).

### Windows

Download `what-<version>-x64-setup.exe` and run it. Nothing else needs to be installed: the app brings its own Python and FFmpeg, and it
installs per user, without administrator rights.

- **"Windows protected your PC":** the installer is not code-signed yet, so SmartScreen
  warns about an unknown publisher. Choose **More info → Run anyway**.
- **First start on an NVIDIA GPU** downloads NVIDIA's CUDA runtime once (about 1.3 GB); the
  window shows progress. Other machines transcribe on the CPU.
- **First Start** downloads the speech model (about 1.5 GB for `medium`); later starts are
  offline.
- **OBS:** if OBS Studio 30 or newer is installed, the installer also adds the What Caption
  Box plugin (see [OBS captions](#obs-captions)). Close OBS before installing.
- Settings, the GPU runtime, and recordings live in `%APPDATA%\What`; uninstalling the app
  leaves that folder in place.

### macOS (Apple Silicon)

Download `what-<version>-arm64.dmg` (or the `-mac.zip`), drag **What** to Applications.
Nothing else needs to be installed: the app brings its own Python and FFmpeg.

- **First launch:** the app is not signed with an Apple Developer ID or notarized, so
  Gatekeeper blocks it ("Apple could not verify 'What'…" or "What is damaged", offering
  Move to Trash). Choose **Done**, then clear the download flag in Terminal and open it:
  ```sh
  xattr -dr com.apple.quarantine /Applications/What.app
  open /Applications/What.app
  ```
  **System Settings → Privacy & Security → Open Anyway** also approves it, but Gatekeeper's
  first-launch check of the app can then take a long time, leaving the app in the Dock with
  no window. If that happens, quit it and use the commands above.
- **Permissions:** allow Microphone, and Screen Recording for **What System Audio** (desktop
  capture). The grant may need repeating after an update because the app is ad-hoc signed.
- **First Start** downloads the speech model; later starts are offline.

See [macOS packaging](docs/packaging_macos.md). This build has had less testing than the
from-source path below.

### Linux

Download `what-<version>-x86_64.AppImage`, `chmod +x` it and run it. It needs **Python 3.12**
(with `venv`) and **FFmpeg** on the machine, and creates its Python environment in
`~/.config/What` on first start (Internet required). See [Linux packaging](docs/packaging_linux.md).
The AppImage is newer than the Windows installer and has had less testing.

Each platform can also run from source (see [Setup](#setup)).

## Platform status

The feature set above is the shared target; live validation is not equal on every platform.

| Platform | Speech engine | Desktop-audio backend | Status |
| --- | --- | --- | --- |
| macOS (Apple Silicon) | WhisperKit (`base`) | CoreAudio tap | Live-validated by the maintainer: mic + desktop capture, replay, corrections, OBS captions. |
| Linux | faster-whisper (`medium`, CUDA or CPU) | FFmpeg + PulseAudio/PipeWire monitor | Automated tests pass; GPU decode and the desktop/replay smoke path validated on one RTX 3080 machine. Broad live acceptance is still open. |
| Windows | faster-whisper (CUDA or CPU) | WASAPI loopback of the default output (no extra driver) | Validated on one Windows 11 + GTX 1080 machine: setup script, GUI launch, DirectShow mic capture, loopback desktop capture, GPU decode. Broad live acceptance is still open. |

These results are not a full v0.1 release certification. See the
[project brief](docs/PROJECT_BRIEF.md) and [known limitations](KNOWN_ISSUES.md).

## Setup

Running from source (all platforms; the [downloads](#download) above are the easy path). All platforms need **Python 3.12**, **Node.js/npm**, and **FFmpeg on PATH**. First model
initialization needs Internet access to download the speech model; later cached loads are
local. Per-platform helper scripts live in `scripts/setup/`.

### macOS (Apple Silicon)

Also requires Xcode with Swift 6 or newer. macOS ships an unrelated `what` command, so use
the explicit virtual-environment command below. Live validation is on the maintainer's Mac,
not a matrix of older macOS versions.

```sh
python3.12 -m venv _venv
_venv/bin/python -m pip install -r requirements-macos-service.txt
npm --prefix gui ci
(cd native/WhisperKitWorker && swift build -c release)
_venv/bin/python -m what gui
```

Use the default WhisperKit configuration. `config/mac.toml` is an older CPU configuration,
not the recommended start. The desktop helper build script installs a user LaunchAgent — an
audio helper, not a bundled GUI. See [desktop capture](docs/core_audio_tap_migration.md) and
[WhisperKit setup](native/WhisperKitWorker/README.md).

### Linux

Desktop-audio capture uses FFmpeg's Pulse input against the default output's monitor source,
so it needs **`pactl`** (from `pulseaudio-utils`) and a running PulseAudio server or PipeWire's
PulseAudio compatibility service. A pure-ALSA session is not supported for desktop capture. The
app does not install or replace your audio server.

```sh
scripts/setup/setup_linux.sh          # creates .venv and installs requirements
.venv/bin/python -m what gui
```

For NVIDIA GPUs, `what gui` checks for a usable GPU and, if the CUDA runtime libraries are
missing, installs the `nvidia-cublas-cu12` / `nvidia-cudnn-cu12` wheels into the virtual
environment (first setup can download over 1 GB; set `WHAT_AUTO_INSTALL_CUDA=0` to disable).
If the GPU can't fit the model — unavailable, or another app holds the VRAM — the service
steps down a ladder (int8 → a smaller model → CPU) instead of collapsing straight to a slow
CPU decode. To cap GPU use, set **`WHAT_GPU_MEM_BUDGET_MB`** (e.g. `1500`): the service then
picks the largest model that fits that budget (split across the mic and desktop workers,
count set by `WHAT_GPU_MAX_WORKERS`, default 2) and uses the CPU only if nothing fits. The same
cap is available in the GUI as **Settings → GPU memory limit** on Linux and Windows. No
system NVIDIA driver is installed or changed. See the [Linux smoke test](docs/LINUX_SMOKE_TEST.md).

### Windows

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup\setup_windows.ps1
.\.venv\Scripts\python -m what gui
```

The setup script installs Python 3.12, FFmpeg, and Node.js with `winget` if they are
missing, then builds `.venv` and the GUI dependencies. (Python 3.14 is not supported yet:
some dependencies have no wheels for it.) The `-ExecutionPolicy Bypass` form avoids
changing the machine's script policy.

Microphones are captured through DirectShow. Desktop audio records whatever plays on the
default output device via WASAPI loopback — no Stereo Mix or virtual cable is needed. On an
NVIDIA GPU the first start downloads the CUDA runtime wheels (about 1.3 GB) into `.venv`;
GTX 10-series cards, which lack fast float16, automatically run int8 instead.

The OBS plugin is not built by the setup script. To build it and install it into OBS
(needs the Visual Studio C++ Build Tools and CMake; `scripts\package\build_windows.ps1
-ToolchainOnly` offers to install them), close OBS and run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\package\build_obs_plugin_windows.ps1 -Install
```

To build the installer itself: `npm --prefix gui run dist:win` (see
`scripts\package\build_windows.ps1`).

## Using the GUI

In the GUI, choose Mic and/or Desktop and press Start. Use Settings to select the input
device, publication delay, or a local audio file for testing. On macOS, follow the microphone
and desktop-audio permission prompts.

- Scroll up to review speech; **Return to live** resumes following new speech.
- Cmd- or Ctrl-click a word to replay its recording; untimed or corrected segments use
  passage-level timing. Stop playback with the playback control or Escape.
- Double-click a segment to correct it; Enter saves and Escape cancels.
- Change **Mic device** while running to reopen that input without restarting the service.
  **Transcript playback output** routes replay independently of the system default. Runtime
  switching is implemented with regression tests; hardware acceptance checks are still pending.
- Desktop capture is suppressed during replay. Speaker playback can still reach a live mic.

### Session files

Each run writes two files into its session folder (**File → Show Session Folder**):

- `transcript.txt`: everything that was said, from all sources, in time order. Each block
  shows its time span and source (`Mic` or `Desktop`); review corrections are applied and
  marked `(edited)`.
- `<session_id>.what`: the whole session in one file (each source's recording and segment
  log, corrections, transcript). It is written when the session stops and refreshed after
  edits.

**File → Open Session…** (Cmd/Ctrl+O) opens a `.what` file, also one copied from another
machine. Mic and desktop go back into their own panels, with replay and editing as during a
live session. Pressing **Start** then adds to that session. **File → New Session** clears
the panels so the next Start begins a new one. **File → Save Session As…** writes the
session to a `.what` file of your choice. A session opened from, or saved to, a file outside
the logs folder keeps that file up to date as you edit or continue it.

The same operations are available on the command line: `what session transcript <folder>`,
`what session pack <folder>` and `what session unpack <file.what>`. See
[session files](docs/SESSION_FILES.md) for the formats.

## OBS captions

With `what` running, open [caption-box settings](http://127.0.0.1:8790/caption-box-settings).
Choose Mic/Desktop, font size, padding, and preview dimensions; copy the URL. If port 8790
is occupied, use the actual overlay port reported by the app.

Choose either entry point:

- **Ordinary OBS Browser source:** paste the URL and set its Width/Height explicitly.
- **What Caption Box plugin source:** the Windows installer adds the plugin automatically;
  from source, [build and install it](obs-plugin/BROWSER_CAPTION_BOX.md) (Windows: see
  [Setup → Windows](#windows)). Add a new **What Caption Box** source and paste the same URL. Drag handles to resize; Shift permits independent width/height.
  After a short pause the text reflows at its original font size.

For each independent layout, choose **Create new**, not **Add Existing**. References share
one viewport, so the plugin intentionally disables automatic reflow for shared sources.
Completed lines stay frozen until intentional reflow; height controls whole-line overflow.
The older `/overlay` page and native What Captions source remain available during migration.

## Recordings and privacy

Session recordings, transcripts, and corrections are stored locally in `logs/<session_id>/`.
Older correction exports use `corrections/`. Both directories are ignored by Git, along with
local `.env` files, audio fixtures, and build outputs. A `.what` session file contains the
session's audio recordings, so treat it like the recording itself when sharing it.
Corrections are saved with provenance but do not yet train a model or change
already-published captions.

The normal GUI binds services to loopback. Do not expose controller or overlay ports to the
public Internet; they are local desktop interfaces, not a hardened hosted service.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup and checks, the
[macOS smoke test](docs/MACOS_SMOKE_TEST.md), and the
[Linux smoke test](docs/LINUX_SMOKE_TEST.md) for the user workflow.
For CLI commands, use the virtual-environment `python -m what --help` and the relevant
subcommand's `--help`. [ASR engines](docs/ASR_ENGINES.md) documents engine-specific behavior.
Documents describing older prototypes are historical references; the project brief defines
current scope.

## License

Project-authored code is licensed under **GPL-3.0-or-later**; see [LICENSE](LICENSE).
Third-party dependencies and model weights retain their own licenses; see
[THIRD_PARTY.md](THIRD_PARTY.md). Public source publication and binary distribution are
separate steps. See [publication notes](docs/PUBLICATION.md) before exporting this checkout.
