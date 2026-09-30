"""Prepare NVIDIA user-space libraries (cuBLAS 12, cuDNN 9) for the service.

Driver installation remains the OS's job. Runtime wheels live only in this Python
environment (Linux: nvidia/*/lib on LD_LIBRARY_PATH; Windows: nvidia/*/bin on PATH);
macOS, CPU-only hosts and explicit CPU services skip it.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import sysconfig

CUDA_PACKAGES = ("nvidia-cublas-cu12>=12,<13", "nvidia-cudnn-cu12>=9,<10")
_PROBES = {
    "linux": "import ctypes; ctypes.CDLL('libcublas.so.12'); ctypes.CDLL('libcudnn.so.9')",
    # CTranslate2's Windows wheel ships only the cuDNN dispatcher; the ops library and
    # cuBLAS must be loadable from PATH for the first GPU decode to succeed. winmode=0 uses
    # the standard (PATH-searching) order that CTranslate2 itself loads with.
    "win32": "import ctypes; ctypes.WinDLL('cublas64_12.dll', winmode=0); ctypes.WinDLL('cudnn_ops64_9.dll', winmode=0)",
}


def _loader_layout():
    """(wheel library subdir, loader env var, separator) for this platform."""
    if sys.platform == "win32":
        return "bin", "PATH", ";"
    return "lib", "LD_LIBRARY_PATH", ":"


def install_target(env: dict[str, str]) -> Path | None:
    """WHAT_CUDA_TARGET: a writable directory for the runtime wheels (`pip --target`).

    Packaged apps set it: their bundled Python is not a venv and its folder may be
    read-only, so the wheels go under the user's app-data directory instead.
    """
    raw = (env.get("WHAT_CUDA_TARGET") or "").strip()
    return Path(raw) if raw else None


def library_environment(env: dict[str, str]) -> dict[str, str]:
    result = dict(env)
    subdir, var, sep = _loader_layout()
    roots = {sysconfig.get_path("purelib"), sysconfig.get_path("platlib")}
    target = install_target(env)
    if target is not None:
        roots.add(str(target))
    paths = []
    for root in sorted(filter(None, roots)):
        paths.extend(str(p) for p in sorted((Path(root) / "nvidia").glob(f"*/{subdir}")) if p.is_dir())
    paths.extend(p for p in env.get(var, "").split(sep) if p)
    if paths:
        result[var] = sep.join(dict.fromkeys(paths))
    return result


def libraries_load(env: dict[str, str]) -> bool:
    try:
        return subprocess.run([sys.executable, "-c", _PROBES[sys.platform]], env=env,
                              capture_output=True, timeout=20, **_no_window()).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _no_window() -> dict:
    # A packaged Windows app has no console; don't flash one per helper process.
    flag = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return {"creationflags": flag} if flag else {}


class _InstallLock:
    """Serialize GUI/service launches that share the same environment."""

    def __init__(self, path: Path):
        self._file = open(path, "a+")

    def __enter__(self):
        if os.name == "nt":
            import msvcrt
            # LK_LOCK gives up after ~10 s; keep waiting out a concurrent install (pip's
            # timeout is 900 s), then proceed unlocked rather than hang forever.
            for _ in range(90):
                try:
                    self._file.seek(0)
                    msvcrt.locking(self._file.fileno(), msvcrt.LK_LOCK, 1)
                    break
                except OSError:
                    continue
        else:
            import fcntl
            fcntl.flock(self._file, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        self._file.close()  # releases the lock on both platforms
        return False


def prepare_cuda_environment(env=None, *, device=None) -> dict[str, str]:
    env = dict(os.environ if env is None else env)
    if sys.platform not in _PROBES or device == "cpu":
        return env
    from .gpu import detect_gpu
    gpu = detect_gpu()
    if not gpu.available or gpu.device != "cuda":
        return env
    prepared = library_environment(env)
    if libraries_load(prepared):
        return prepared
    if env.get("WHAT_AUTO_INSTALL_CUDA", "1").lower() in {"0", "false", "no"}:
        print("CUDA runtime: automatic installation disabled; required libraries unavailable.", file=sys.stderr)
        return prepared
    target = install_target(env)
    if target is None and sys.prefix == sys.base_prefix:
        print("CUDA runtime: use a virtual environment to enable automatic dependency installation.", file=sys.stderr)
        return prepared
    # Current faster-whisper/CTranslate2 wheels require CUDA 12 and cuDNN 9.
    from importlib.metadata import version
    ct2_version = tuple(int(part) for part in version("ctranslate2").split(".")[:2])
    if not ((4, 5) <= ct2_version < (5, 0)):
        print("CUDA runtime: automatic setup requires CTranslate2 >=4.5,<5.", file=sys.stderr)
        return prepared
    try:
        lock_dir = target if target is not None else Path(sys.prefix)
        lock_dir.mkdir(parents=True, exist_ok=True)
        with _InstallLock(lock_dir / ".what-cuda-install.lock"):
            prepared = library_environment(env)
            if not libraries_load(prepared):
                print("CUDA runtime: NVIDIA GPU detected; installing cuBLAS 12 and cuDNN 9 "
                      "in the app environment. First setup may take several minutes.", file=sys.stderr, flush=True)
                where = ["--target", str(target)] if target is not None else []
                # ~1.3 GB of wheels: allow for slow connections.
                subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                                "--no-input", *where, *CUDA_PACKAGES], env=env, stdin=subprocess.DEVNULL,
                               check=True, timeout=3600, **_no_window())
                prepared = library_environment(env)
                if not libraries_load(prepared):
                    raise RuntimeError("installed libraries could not be loaded")
                print("CUDA runtime: cuBLAS and cuDNN ready.", file=sys.stderr, flush=True)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"CUDA runtime setup failed: {exc}. Service preflight will report whether CPU fallback is needed.",
              file=sys.stderr, flush=True)
    return prepared


def prepare_service_runtime(device=None) -> None:
    prepared = prepare_cuda_environment(device=device)
    if sys.platform == "win32":
        # Windows resolves DLLs from PATH at LoadLibrary time, so updating this process's
        # PATH before CTranslate2 first touches cuBLAS/cuDNN is enough; no re-exec needed.
        os.environ["PATH"] = prepared.get("PATH", os.environ.get("PATH", ""))
        return
    if prepared.get("LD_LIBRARY_PATH", "") != os.environ.get("LD_LIBRARY_PATH", ""):
        # Linux's loader reads LD_LIBRARY_PATH at process startup. Updating os.environ
        # alone cannot repair CTranslate2's later dlopen calls in this process.
        os.execve(sys.executable, [sys.executable, *sys.orig_argv[1:]], prepared)


if __name__ == "__main__":
    # `python -m what.cuda_runtime`: fetch the GPU runtime up front (the packaged GUI runs
    # this before starting the controller, so the download can't time out a service start).
    prepare_cuda_environment()
