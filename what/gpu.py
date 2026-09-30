from __future__ import annotations

from dataclasses import dataclass
import platform


@dataclass
class GpuInfo:
    available: bool
    device: str
    device_count: int
    backend: str
    reason: str
    accelerators: tuple[str, ...] = ()
    engines: tuple[str, ...] = ()
    recommended_engine: str = "faster_whisper"


def detect_gpu() -> GpuInfo:
    if platform.system() == "Darwin" and platform.machine().lower() in {"arm64", "aarch64"}:
        return GpuInfo(
            available=True,
            device="apple_silicon",
            device_count=1,
            backend="coreml",
            reason="Apple Silicon available; WhisperKit worker required",
            accelerators=("apple_gpu", "apple_neural_engine"),
            engines=("whisperkit", "whisper_cpp"),
            recommended_engine="whisperkit",
        )
    try:
        import ctranslate2
    except Exception as exc:  # pragma: no cover - optional dependency path
        return GpuInfo(
            available=False,
            device="cpu",
            device_count=0,
            backend="ctranslate2",
            reason=f"ctranslate2 import failed: {type(exc).__name__}",
            accelerators=("cpu",),
            engines=("faster_whisper",),
        )

    try:
        # CTranslate2 4.x exposes get_cuda_device_count(); older builds used
        # get_device_count("cuda"). Support both so a version bump can't silently
        # drop us to CPU (that AttributeError used to read as "cuda query failed").
        if hasattr(ctranslate2, "get_cuda_device_count"):
            count = int(ctranslate2.get_cuda_device_count())
        else:
            count = int(ctranslate2.get_device_count("cuda"))
    except Exception as exc:  # pragma: no cover - defensive
        return GpuInfo(
            available=False,
            device="cpu",
            device_count=0,
            backend="ctranslate2",
            reason=f"cuda query failed: {type(exc).__name__}",
            accelerators=("cpu",),
            engines=("faster_whisper",),
        )

    if count <= 0:
        return GpuInfo(
            available=False,
            device="cpu",
            device_count=0,
            backend="ctranslate2",
            reason="no cuda devices",
            accelerators=("cpu",),
            engines=("faster_whisper",),
        )

    return GpuInfo(
        available=True,
        device="cuda",
        device_count=count,
        backend="ctranslate2",
        reason="ok",
        accelerators=("cuda",),
        engines=("faster_whisper",),
        recommended_engine="faster_whisper",
    )


def nvidia_memory(timeout: float = 3.0) -> list[dict]:
    """Name and total/used VRAM (MiB) per NVIDIA GPU via nvidia-smi; [] when unavailable.

    Informational only (shown next to the GPU memory limit setting); the ASR path never
    depends on it.
    """
    import shutil
    import subprocess

    exe = shutil.which("nvidia-smi")
    if not exe:
        return []
    kwargs = {}
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # no console flash on Windows
    try:
        out = subprocess.run(
            [exe, "--query-gpu=name,memory.total,memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=timeout, **kwargs,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    gpus = []
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 3:
            continue
        try:
            gpus.append({"name": parts[0], "total_mb": int(float(parts[1])), "used_mb": int(float(parts[2]))})
        except ValueError:
            continue
    return gpus
