import queue
import threading
from dataclasses import dataclass
from typing import Any


@dataclass
class ServiceConfig:
    host: str
    port: int
    sse_path: str
    ws_path: str
    http_path: str
    pair_path: str
    local_pair: bool
    mdns_name: str
    mdns_enabled: bool
    advertise_host: str | None
    max_clients: int


@dataclass
class ClientState:
    client_id: str
    transport: str
    stop_event: threading.Event
    thread: threading.Thread
    queue: queue.Queue[bytes] | None
    decoder_proc: Any | None
    log_path: str
    session_dir: str
    transcript: list[str]
