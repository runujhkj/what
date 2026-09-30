from ..pair import request_pair_token


def handle_pair(args, cfg: dict) -> None:
    host = args.host or None
    port = args.port or cfg.get("service", {}).get("port", 8765)
    pair_path = args.pair_path or cfg.get("service", {}).get("pair_path", "/pair")
    token = request_pair_token(args.session_key, host, port, pair_path)
    print(token)
