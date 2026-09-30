"""Sidecar controller for managing the transcription service process."""


def run_controller(*args, **kwargs):
    from .run import run_controller as _run_controller

    return _run_controller(*args, **kwargs)


__all__ = ["run_controller"]
