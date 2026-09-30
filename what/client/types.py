from dataclasses import dataclass


@dataclass
class ClientConfig:
    transport: str
    target_host: str
    target_port: int
    target_ws_path: str
    target_sse_path: str
