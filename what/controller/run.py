import logging
import os

import uvicorn

from .api import create_controller_app
from .state import ControllerState
from .types import ControllerConfig

# High-frequency polling endpoints that would otherwise flood the terminal with
# dozens of 200 OK lines per second.
_MUTED_PATHS = frozenset({
    "/control/session/log",
    "/control/status",
    "/control/stream/logs",
    "/control/stream/events",
})


class _DropPollingAccess(logging.Filter):
    """Suppress 200 access-log entries for endpoints polled every few seconds."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        # uvicorn format ends with '%d' so the message ends "HTTP/1.x" 200 (no trailing space).
        # Check for '" 200' without requiring a trailing character.
        if '" 200' in msg:
            for path in _MUTED_PATHS:
                if path in msg:
                    return False
        return True


def run_controller(cfg: ControllerConfig) -> None:
    # Set before uvicorn starts so child processes (Whisper service, transcription
    # client) inherit it and tokenizers never initialises its thread pool — preventing
    # the "current process just got forked after parallelism has been used" warning.
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    logging.getLogger("uvicorn.access").addFilter(_DropPollingAccess())

    state = ControllerState()
    app = create_controller_app(cfg, state)
    uvicorn.run(
        app,
        host=cfg.host,
        port=cfg.port,
        log_level="info",
        timeout_graceful_shutdown=2,
    )
