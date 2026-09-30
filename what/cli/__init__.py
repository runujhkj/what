"""CLI command parsing and handlers."""


def main(*args, **kwargs):
    from .main import main as _main

    return _main(*args, **kwargs)


__all__ = ["main"]
