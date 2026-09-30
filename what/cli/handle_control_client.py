from ..controller.client import apply, get_gpu, get_status, start, stop
from ..env import get_env


def handle_control_client(args) -> None:
    base_url = args.base_url or get_env("WHAT_CONTROL_URL") or "http://127.0.0.1:8780"
    if args.action == "status":
        print(get_status(base_url))
        return
    if args.action == "gpu":
        print(get_gpu(base_url))
        return
    if args.action == "stop":
        print(stop(base_url))
        return
    payload = {
        "profile": args.profile,
        "engine": args.engine,
        "device": args.device,
        "device_index": args.device_index,
        "compute_type": args.compute_type,
        "model_size": args.model_size,
        "beam_size": args.beam_size,
        "language": args.language,
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    if args.action == "start":
        print(start(base_url, payload))
        return
    if args.action == "apply":
        print(apply(base_url, payload))
        return
