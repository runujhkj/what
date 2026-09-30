import os
import subprocess
import sys
from typing import Dict

import shutil

from .types import DiscoveredService, SERVICE_TYPE


def discover_services_avahi(debug: bool = False) -> Dict[str, DiscoveredService]:
    services: Dict[str, DiscoveredService] = {}
    service_type = SERVICE_TYPE
    if service_type.endswith(".local."):
        service_type = service_type[:-7]
    for candidate in (service_type, SERVICE_TYPE):
        cmd = ["avahi-browse", "-rtp", candidate]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except OSError:
            return services
        if result.returncode == 0 and result.stdout.strip():
            break
        if debug:
            sys.stderr.write(f"discovery: avahi-browse empty rc={result.returncode} for {candidate}\n")
    else:
        return services
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line.startswith("="):
            continue
        parts = line.split(";")
        if len(parts) < 9:
            continue
        name = parts[3]
        host = parts[7]
        try:
            port = int(parts[8])
        except ValueError:
            continue
        if name and host and port:
            services[name] = DiscoveredService(name=name, host=host, port=port)
    if debug:
        sys.stderr.write(f"discovery: avahi found={len(services)}\n")
    return services


def can_use_avahi() -> bool:
    return shutil.which("avahi-browse") is not None and os.getenv("WHAT_DISCOVERY_METHOD", "auto").lower() in {
        "auto",
        "avahi",
    }
