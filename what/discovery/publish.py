import os
import socket
import sys

from zeroconf import ServiceInfo, Zeroconf

from .hosts import guess_advertise_host
from .types import SERVICE_TYPE


def publish_service(name: str, host: str, port: int, advertise_host: str | None = None) -> Zeroconf:
    debug = os.getenv("WHAT_MDNS_DEBUG") == "1"
    zeroconf = Zeroconf()
    orig_host = host
    if advertise_host:
        host = advertise_host
    elif host == "0.0.0.0":
        host = guess_advertise_host()
    if debug:
        sys.stderr.write(
            f"mdns: publish name={name} port={port} bind_host={orig_host} advertise_host={host}\n"
        )
    info = ServiceInfo(
        SERVICE_TYPE,
        f"{name}.{SERVICE_TYPE}",
        addresses=[socket.inet_aton(host)],
        port=port,
        properties={},
        server=f"{name}.local.",
    )
    if debug:
        sys.stderr.write(f"mdns: addresses={info.parsed_addresses()}\n")
    zeroconf.register_service(info)
    return zeroconf
