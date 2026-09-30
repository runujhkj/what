from dataclasses import dataclass


@dataclass
class ControllerConfig:
    host: str
    port: int
    service_host: str
    service_port: int
    config_path: str | None
    settings_path: str | None = None
