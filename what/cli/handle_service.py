import sys

from .builders import apply_engine_defaults, build_asr_cfg, build_audio_cfg, build_output_cfg, build_vad_cfg
from .service_tests import run_service_tests
from ..env import get_env, get_env_int
from ..gpu import detect_gpu
from ..service import ServiceConfig, run_service


def handle_service(args, cfg: dict) -> None:
    from ..cuda_runtime import prepare_service_runtime
    prepare_service_runtime(device=args.device or cfg.get("asr", {}).get("device"))
    auto_cpu = False
    gpu = detect_gpu() if args.device is None else None
    if gpu is not None and gpu.available is False:
        auto_cpu = True
        cfg = cfg.copy()
        cfg["audio"] = {**cfg.get("audio", {}), **cfg.get("profiles", {}).get("cpu_friendly", {}).get("audio", {})}
        cfg["asr"] = {**cfg.get("asr", {}), **cfg.get("profiles", {}).get("cpu_friendly", {}).get("asr", {})}
        cfg["output"] = {**cfg.get("output", {}), **cfg.get("profiles", {}).get("cpu_friendly", {}).get("output", {})}
    audio_cfg = build_audio_cfg(args, cfg)
    vad_cfg = build_vad_cfg(args, cfg)
    asr_cfg = build_asr_cfg(args, cfg)
    apply_engine_defaults(args, cfg, audio_cfg, asr_cfg)
    output_cfg = build_output_cfg(args, cfg)
    if run_service_tests(args, audio_cfg, vad_cfg, asr_cfg):
        return
    service_cfg = ServiceConfig(
        host=args.host or get_env("WHAT_SERVICE_HOST") or cfg["service"]["host"],
        port=args.port or get_env_int("WHAT_SERVICE_PORT") or cfg["service"]["port"],
        sse_path=args.sse_path or get_env("WHAT_SERVICE_SSE_PATH") or cfg["service"]["sse_path"],
        ws_path=args.ws_path or get_env("WHAT_SERVICE_WS_PATH") or cfg["service"]["ws_path"],
        http_path=args.http_path or get_env("WHAT_SERVICE_HTTP_PATH") or cfg["service"]["http_path"],
        pair_path=args.pair_path or get_env("WHAT_SERVICE_PAIR_PATH") or cfg["service"]["pair_path"],
        local_pair=(get_env("WHAT_SERVICE_LOCAL_PAIR", "1") != "0")
        and cfg["service"].get("local_pair", True),
        mdns_name=args.mdns_name or get_env("WHAT_SERVICE_MDNS_NAME") or cfg["service"]["mdns_name"],
        mdns_enabled=not args.no_mdns
        and (get_env("WHAT_SERVICE_MDNS_ENABLED", "1") != "0")
        and cfg["service"].get("mdns_enabled", True),
        advertise_host=args.advertise_host
        or get_env("WHAT_SERVICE_ADVERTISE_HOST")
        or cfg["service"].get("advertise_host"),
        max_clients=args.max_clients or get_env_int("WHAT_SERVICE_MAX_CLIENTS") or cfg["service"]["max_clients"],
    )
    try:
        if auto_cpu:
            # Surface the detect_gpu reason so a CUDA/driver/lib problem is
            # diagnosable from the log instead of a bare "no GPU found".
            print(f"no GPU found ({gpu.reason}); using cpu_friendly profile")
        run_service(audio_cfg, vad_cfg, asr_cfg, output_cfg, service_cfg)
    except KeyboardInterrupt:
        sys.stderr.write("service stopped\n")
