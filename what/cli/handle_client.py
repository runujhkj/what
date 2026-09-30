import asyncio
import sys

from .builders import build_audio_cfg, build_input_cfg
from ..client import ClientConfig, run_client
from ..env import get_env, get_env_int
from ..pair import request_pair_token


def handle_client(args, cfg: dict) -> None:
    audio_cfg = build_audio_cfg(args, cfg)
    input_cfg = build_input_cfg(args, cfg)
    session_key = args.session_key or args.session_key_pos
    if not args.pair and not session_key and not args.local:
        raise ValueError("client requires --pair, --session-key, a positional session key, or --local")
    client_cfg = ClientConfig(
        transport=args.transport or cfg["client"]["transport"],
        target_host=args.host or get_env("WHAT_CLIENT_HOST") or cfg["client"]["target_host"],
        target_port=args.port or get_env_int("WHAT_CLIENT_PORT") or cfg["client"]["target_port"],
        target_ws_path=args.ws_path or cfg["client"]["target_ws_path"],
        target_sse_path=get_env("WHAT_CLIENT_SSE_PATH") or cfg["client"]["target_sse_path"],
    )
    client_id = args.client_id or get_env("WHAT_CLIENT_ID")
    token = args.pair or get_env("WHAT_PAIR_TOKEN")
    if not token:
        pair_path = cfg.get("service", {}).get("pair_path", "/pair")
        pair_host = args.host or get_env("WHAT_CLIENT_HOST") or cfg["client"].get("target_host")
        service_host = cfg.get("service", {}).get("host", "127.0.0.1")
        preferred_host = "127.0.0.1" if service_host == "0.0.0.0" else service_host
        pair_port = (
            args.port
            or get_env_int("WHAT_CLIENT_PORT")
            or cfg["client"].get("target_port")
            or cfg.get("service", {}).get("port", 8765)
        )
        try:
            if args.local:
                pair_host = pair_host or "127.0.0.1"
                sys.stderr.write("pairing: local mode enabled\n")
            if not pair_host:
                pair_host = "127.0.0.1"
                sys.stderr.write(f"pairing: defaulting host to {pair_host}\n")
            sys.stderr.write(f"pairing: requesting token from http://{pair_host}:{pair_port}{pair_path}\n")
            token = request_pair_token(session_key or "", pair_host, pair_port, pair_path)
        except KeyboardInterrupt:
            sys.stderr.write("pairing cancelled\n")
            return
    env_captions = get_env("WHAT_CAPTIONS_ON")
    if args.captions_on is None:
        captions_on = True if env_captions is None else env_captions == "1"
    else:
        captions_on = args.captions_on
    display_mode = args.display_mode or cfg["output"].get("text_mode", "delta")
    block_clear = cfg["output"].get("text_block_clear", False)
    if args.block_clear:
        block_clear = True
    if args.no_block_clear:
        block_clear = False
    normalize = cfg["output"].get("text_normalize", False)
    if args.normalize:
        normalize = True
    if args.no_normalize:
        normalize = False
    try:
        asyncio.run(
            run_client(
                client_cfg=client_cfg,
                input_cfg=input_cfg,
                audio_cfg=audio_cfg,
                token=token,
                client_name=client_id,
                captions_on=captions_on,
                captions_mode=display_mode,
                captions_block_clear=block_clear,
                captions_normalize=normalize,
                transcript_prefix=args.transcript_prefix,
                event_prefix=args.event_prefix,
            )
        )
    except KeyboardInterrupt:
        sys.stderr.write("client stopped\n")
