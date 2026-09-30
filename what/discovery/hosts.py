import socket


def _is_private_ipv4(ip: str) -> bool:
    parts = ip.split(".")
    if len(parts) != 4:
        return False
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return False
    if nums[0] == 10:
        return True
    if nums[0] == 172 and 16 <= nums[1] <= 31:
        return True
    if nums[0] == 192 and nums[1] == 168:
        return True
    return False


def _is_link_local(ip: str) -> bool:
    return ip.startswith("169.254.")


def guess_advertise_host() -> str:
    try:
        import ifaddr
    except Exception:
        ifaddr = None
    if ifaddr is not None:
        candidates: list[tuple[int, str]] = []
        for adapter in ifaddr.get_adapters():
            name = (adapter.nice_name or "").lower()
            penalty = 0
            if any(tag in name for tag in ("virtual", "hyper", "vbox", "docker", "wsl", "vpn", "vmware")):
                penalty = -1
            for ip in adapter.ips:
                addr = ip.ip
                if not isinstance(addr, str):
                    continue
                if addr.startswith("127.") or _is_link_local(addr):
                    continue
                score = 0
                if _is_private_ipv4(addr):
                    if addr.startswith("192.168."):
                        score = 3
                    elif addr.startswith("10."):
                        score = 2
                    else:
                        score = 1
                candidates.append((score + penalty, addr))
        if candidates:
            candidates.sort(reverse=True)
            return candidates[0][1]
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return socket.gethostbyname(socket.gethostname())
    finally:
        sock.close()
