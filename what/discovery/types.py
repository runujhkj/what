from dataclasses import dataclass


SERVICE_TYPE = "_what._tcp.local."


@dataclass
class DiscoveredService:
    name: str
    host: str
    port: int
