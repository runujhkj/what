from ..view import view_sse


def handle_view(args) -> None:
    sse_url = args.sse_url
    if not sse_url:
        host = args.host or "127.0.0.1"
        port = args.port or 8765
        path = args.sse_path or "/events"
        sse_url = f"http://{host}:{port}{path}"
    block_clear = args.block_clear
    if args.no_block_clear:
        block_clear = False
    normalize = True
    if args.normalize:
        normalize = True
    if args.no_normalize:
        normalize = False
    view_sse(
        sse_url,
        args.client_id,
        args.session_id,
        args.raw,
        display_mode=args.display_mode,
        block_clear=block_clear,
        normalize=normalize,
    )
