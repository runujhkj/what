# Linux packaging (AppImage)

Status: initial scaffold, 2026-09-23. The path/runtime layer, electron-builder config, and
Python staging are in place and unit-tested; a full AppImage build and a run of the produced
image are **not yet verified**. This documents the model and the remaining steps.

## Model

`what` is an Electron front-end plus a Python service/client. The Linux delivery is a single
**AppImage** built with electron-builder from `gui/`.

- The Electron app (the `gui/` tree) is packed into the AppImage as usual.
- The Python side — the `what` package, `config/`, and the requirements files — is staged by
  `scripts/package/prepare_python_runtime.sh` into `gui/build/pyruntime` and bundled
  **read-only** under `resources/pyruntime` via electron-builder `extraResources`.
- **No virtualenv and no model weights are bundled.** On first launch the app builds a venv
  in the user's data dir and installs only the third-party **dependencies** into it (the list
  in `gui/lib/python_runtime.js`, mirroring pyproject's service+client extras plus
  setuptools). The `what` package itself is **not** installed: it is imported from the
  read-only bundled source, because `python -m what` runs with cwd = `resources/pyruntime`,
  which also holds `config/`. Installing the package would fail — an editable install writes
  into the read-only source, and a wheel build needs LICENSE/README the staged tree omits.
  Model weights download on first transcription as they already do; NVIDIA runtime wheels are
  handled by the existing `what/cuda_runtime.py` auto-install.

This mirrors how the app already provisions things at runtime rather than trying to produce a
fully self-contained binary for v0.1. A future version can embed a relocatable interpreter
(e.g. python-build-standalone) for a no-Python-required image.

## How paths resolve

`gui/lib/runtime_paths.js` centralizes dev-vs-packaged resolution:

| | Source checkout (dev) | Packaged AppImage |
| --- | --- | --- |
| Python tree (`pythonRoot`) | repo root (`gui/..`) | `resources/pyruntime` |
| Interpreter | repo `.venv`/`_venv`, else `python3` | per-user venv (below) |
| Logs | `<repo>/logs` | `<userData>/logs` (writable) |

`gui/lib/python_runtime.js` owns the per-user venv: `<userData>/pyvenv`, created on first run
and populated from `requirements-service.txt`. `main.js` runs this only when `app.isPackaged`
and sets `WHAT_PYTHON` to the venv interpreter, so a dev checkout is untouched.

## Build

```sh
cd gui
npm ci
npm run dist:linux    # stages pyruntime, then runs electron-builder --linux AppImage
```

Output lands in `gui/dist/what-<version>-<arch>.AppImage`. `npm run prepare:pyruntime`
stages the Python tree on its own if you want to inspect it.

Prerequisites on the build host: Node/npm, Python 3.12 (for the staged tree; not embedded),
and electron-builder's own toolchain (downloaded on first build). The **target** machine needs
Python 3.12 and, on first run, internet access to install dependencies and the model.

## Verified so far

- `runtime_paths.js` and `python_runtime.js` logic (`gui/tests/*` via `npm test`).
- `prepare_python_runtime.sh` stages the source tree (136 files) deterministically.
- `main.js` still resolves the CLI/interpreter/logs in dev mode (behavior-preserving).

## Not yet done

- Run `npm run dist:linux` on a clean host and confirm the AppImage launches, provisions its
  venv, and reaches a live transcript. (Requires downloading electron-builder tooling.)
- App icon and desktop metadata (`build/icon.png`, StartupWMClass) for a polished launcher.
- Decide whether to pre-warm dependencies at build time vs first run for offline installs.
- Windows/macOS targets (out of scope for the Linux v0.1 image).
