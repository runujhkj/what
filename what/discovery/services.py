import os
import sys
from typing import Dict

from .avahi import can_use_avahi, discover_services_avahi
from .types import DiscoveredService
from .zeroconf import discover_services_zeroconf, wants_zeroconf


def discover_services(timeout_s: float = 2.0) -> Dict[str, DiscoveredService]:
    timeout_s = float(os.getenv("WHAT_DISCOVERY_TIMEOUT", timeout_s))
    debug = os.getenv("WHAT_DISCOVERY_DEBUG") == "1"
    if debug:
        method = os.getenv("WHAT_DISCOVERY_METHOD", "auto").lower()
        sys.stderr.write(f"discovery: start timeout_s={timeout_s} method={method}\n")
    services: Dict[str, DiscoveredService] = {}

    if wants_zeroconf():
        services = discover_services_zeroconf(timeout_s=timeout_s, debug=debug)

    method = os.getenv("WHAT_DISCOVERY_METHOD", "auto").lower()
    if (method == "auto" and not services) or method == "avahi":
        if can_use_avahi():
            if debug:
                sys.stderr.write("discovery: fallback to avahi-browse\n")
            services.update(discover_services_avahi(debug=debug))
        elif debug:
            sys.stderr.write("discovery: avahi-browse not found\n")

    if debug:
        sys.stderr.write(f"discovery: total={len(services)}\n")
    return services
