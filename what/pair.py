import json
import urllib.error
import urllib.parse
import urllib.request

from .discovery import discover_services


def request_pair_token(
    session_key: str,
    host: str | None,
    port: int,
    pair_path: str,
    timeout_s: float = 5.0,
) -> str:
    if not host:
        services = discover_services()
        if not services:
            raise RuntimeError("No what service discovered on LAN")
        first = next(iter(services.values()))
        host = first.host
        port = first.port

    base_url = f"http://{host}:{port}{pair_path}"
    url = base_url
    req = urllib.request.Request(url, method="POST")
    req.add_header("X-What-Session", session_key)

    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            payload = json.loads(resp.read().decode("ascii"))
            token = payload.get("token")
            if not token:
                raise RuntimeError("No token returned by server")
            return token
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("ascii")
        except Exception:
            body = ""
        if exc.code == 403 and not body:
            q = urllib.parse.urlencode({"session_key": session_key})
            url = f"{base_url}?{q}"
            with urllib.request.urlopen(url, data=b"", timeout=timeout_s) as resp:
                payload = json.loads(resp.read().decode("ascii"))
                token = payload.get("token")
                if not token:
                    raise RuntimeError("No token returned by server") from exc
                return token
        raise RuntimeError(f"pair failed: {exc.code} {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"pair failed: {exc.reason}") from exc
