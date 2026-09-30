import os
import socket
import sys
import time
from typing import Dict

from zeroconf import IPVersion, InterfaceChoice, ServiceBrowser, Zeroconf

from .types import DiscoveredService, SERVICE_TYPE


def discover_services_zeroconf(timeout_s: float, debug: bool) -> Dict[str, DiscoveredService]:
    services: Dict[str, DiscoveredService] = {}
    zeroconf = Zeroconf(interfaces=InterfaceChoice.All, ip_version=IPVersion.V4Only)

    class _Listener:
        def add_service(self, zc: Zeroconf, service_type: str, name: str) -> None:
            info = zc.get_service_info(service_type, name)
            if not info:
                return
            if debug:
                addrs = info.parsed_addresses() if hasattr(info, "parsed_addresses") else []
                sys.stderr.write(f"discovery: name={name} port={info.port} addresses={addrs}\n")
            host = ""
            for addr in info.addresses or []:
                if len(addr) == 4:
                    host = socket.inet_ntoa(addr)
                    break
            if not host:
                return
            services[name] = DiscoveredService(name=name, host=host, port=info.port)

        def update_service(self, zc: Zeroconf, service_type: str, name: str) -> None:
            return

        def remove_service(self, zc: Zeroconf, service_type: str, name: str) -> None:
            return

    listener = _Listener()
    browser = ServiceBrowser(zeroconf, SERVICE_TYPE, listener)
    time.sleep(timeout_s)
    browser.cancel()
    zeroconf.close()
    return services


def wants_zeroconf() -> bool:
    method = os.getenv("WHAT_DISCOVERY_METHOD", "auto").lower()
    return method in {"auto", "zeroconf"}
