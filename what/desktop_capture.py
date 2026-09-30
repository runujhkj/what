"""Emit desktop PCM (16 kHz mono s16le on stdout) for Electron's replay-suppressed client.

Linux captures the PulseAudio monitor through ffmpeg. Windows records the default output
directly with WASAPI loopback, so no Stereo Mix or virtual cable is needed; naming a
DirectShow device (e.g. Stereo Mix, "CABLE Output") uses ffmpeg against it instead.
"""
import argparse
import os
import sys

from .desktop_audio import build_desktop_input_args


def capture_command(device: str = "default", backend: str = "auto") -> list[str]:
    return ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "warning",
            *build_desktop_input_args(backend, device),
            "-ac", "1", "-ar", "16000", "-acodec", "pcm_s16le", "-f", "s16le", "pipe:1"]


SAMPLE_RATE = 16000
LOOPBACK_DEVICES = {"", "default", "loopback"}


def to_pcm16_mono(frames) -> bytes:
    """float32 frames (n, channels) in [-1, 1] -> little-endian int16 mono bytes."""
    import numpy as np

    mono = frames.mean(axis=1) if frames.ndim == 2 else frames
    return (np.clip(mono, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()


def run_wasapi_loopback(out, block_ms: int = 100) -> None:
    """Stream the default output device's mix to `out` until the reader goes away.

    WASAPI converts to 16 kHz in shared mode and keeps delivering (silent) frames when
    nothing is playing, so the stream stays continuous for the transcription pipeline.
    """
    import warnings

    import soundcard

    # Gaps while the output is idle are reported as "data discontinuity"; they are expected.
    warnings.filterwarnings("ignore", category=soundcard.SoundcardRuntimeWarning)
    speaker = soundcard.default_speaker()
    loopback = soundcard.get_microphone(speaker.id, include_loopback=True)
    sys.stderr.write(f"desktop capture: WASAPI loopback of '{speaker.name}'\n")
    sys.stderr.flush()
    frames = SAMPLE_RATE * block_ms // 1000
    with loopback.recorder(samplerate=SAMPLE_RATE, blocksize=frames) as recorder:
        while True:
            try:
                out.write(to_pcm16_mono(recorder.record(numframes=frames)))
                out.flush()
            except (BrokenPipeError, OSError):
                return  # Electron closed the pipe: capture stopped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default="default")
    parser.add_argument("--backend", default="auto")
    args = parser.parse_args()
    if os.name == "nt" and args.device.strip().lower() in LOOPBACK_DEVICES:
        try:
            run_wasapi_loopback(sys.stdout.buffer)
        except KeyboardInterrupt:
            pass
        except Exception as exc:  # noqa: BLE001 - report any audio-stack failure to the GUI
            sys.stderr.write(f"Desktop capture failed: WASAPI loopback unavailable ({exc}). "
                             "Enable 'Stereo Mix' or install VB-Cable and select it instead.\n")
            raise SystemExit(1) from exc
        return
    try:
        command = capture_command(args.device, args.backend)
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"Desktop capture failed: {exc}\n")
        raise SystemExit(1) from exc
    if os.name == "nt":
        # Windows has no exec Electron can keep tracking, so run ffmpeg as a child that
        # inherits our stdout (Electron's pipe). Electron tears the tree down with
        # taskkill /T, so ffmpeg is stopped even though this wrapper is its parent.
        import subprocess
        # Pass the handles explicitly: under a windowless parent (pythonw, as the GUI runs
        # it) Windows only hands a child our stdout when told to, else ffmpeg's PCM is lost.
        proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=sys.stdout, stderr=sys.stderr)
        try:
            raise SystemExit(proc.wait())
        except KeyboardInterrupt:
            proc.terminate()
            raise SystemExit(proc.wait())
    # POSIX: replace this process so Electron owns and stops the actual capture process.
    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
