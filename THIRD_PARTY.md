# Licensing and third-party components

Project-authored code is offered under GNU GPL version 3 or, at your option, any later
version (SPDX: GPL-3.0-or-later). The full license is in LICENSE. This choice covers the
Python application, GUI, and native integration code in this repository unless a file
carries another notice.

Dependencies retain their own licenses. In a source checkout they are resolved by package
managers or installed separately; the source tree does not redistribute their binaries or
model weights. The Windows installer does bundle binaries; see the next section.
Notable components include:

- OBS/libobs: GPL-2.0-or-later, as stated in its source headers. The OBS plugin links to
  the user's OBS installation. [OBS source](https://github.com/obsproject/obs-studio).
- WhisperKit / argmax-oss-swift: MIT; see its pinned checkout license when building the
  Swift worker. [Upstream](https://github.com/argmaxinc/argmax-oss-swift).
- Electron: MIT, with additional Chromium and other third-party notices in its distribution.
  [Licensing](https://www.electronjs.org/docs/latest/tutorial/about#license).
- Faster-Whisper and CTranslate2: separate optional engine dependencies; preserve their
  upstream notices if distributing them.
- FFmpeg: installed externally from source checkouts; bundled in the Windows installer and the macOS app (below).
- Model weights: downloaded separately. Consult the selected model's license and model card.

## Components bundled in the Windows installer

The installer (built by `scripts/package/build_windows.ps1`; exact versions pinned in
`scripts/package/windows_pins.json`) redistributes these binaries. Their license texts
ship inside the installed app:

- **Electron** (MIT) and Chromium's third-party notices: `LICENSE.electron.txt` and
  `LICENSES.chromium.html` in the install folder.
- **CPython 3.12** from [python-build-standalone](https://github.com/astral-sh/python-build-standalone)
  (Python Software Foundation License, plus the notices of its bundled libraries):
  `resources\python\`.
- **Python packages** preinstalled into that interpreter (faster-whisper, CTranslate2,
  onnxruntime, PyAV, NumPy, FastAPI, uvicorn, websockets, zeroconf, webrtcvad-wheels,
  soundcard, and their dependencies), each under its own license: see the `LICENSE*` files
  in each `*.dist-info` folder under `resources\python\Lib\site-packages\`.
- **FFmpeg** (GPL-3.0; the [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) "essentials"
  build, configured with `--enable-gpl --enable-version3`): `resources\bin\ffmpeg.exe`,
  license in `resources\bin\FFMPEG-LICENSE.txt`. The corresponding source is the FFmpeg
  release of the same version from <https://ffmpeg.org/releases/>, with the build
  configuration published by gyan.dev. To satisfy GPL source-availability for this
  binary independently of those sites, attach the matching FFmpeg source tarball to each
  GitHub release that ships the installer.
- **What Caption Box OBS plugin** (this project, GPL-3.0-or-later) links against libobs
  (GPL-2.0-or-later, used under its "or later" option) from the user's OBS installation.

Not bundled: NVIDIA cuBLAS/cuDNN (downloaded from PyPI on first start on NVIDIA machines,
under NVIDIA's license) and the Whisper model weights (downloaded from Hugging Face; see
each model card).

GPLv3 can be combined with GPLv2-or-later code when choosing the latter's v3 option;
see the [GNU compatibility explanation](https://www.gnu.org/licenses/gpl-faq.html#v2v3Compatibility).
This inventory is a good-faith summary, not legal advice. Re-check it when the bundled
components or their versions change.

## Components bundled in the macOS app

The app (built by `scripts/package/build_macos.sh`; pins in `scripts/package/macos_pins.json`)
also redistributes: Electron (as above); CPython from python-build-standalone with the
Python packages listed in `gui/lib/python_runtime.js`; the WhisperKit worker
(`native/WhisperKitWorker`, with its Swift package dependencies, see `Package.resolved`); and
a static arm64 **FFmpeg** (GPL) from <https://github.com/eugeneware/ffmpeg-static> at
`Contents/Resources/bin/ffmpeg`. The corresponding FFmpeg source is at
<https://ffmpeg.org/releases/>.
