from .builders import apply_engine_defaults, build_asr_cfg, build_audio_cfg, build_input_cfg, build_output_cfg, build_vad_cfg
from .helpers import ensure_log_dir
from ..gpu import detect_gpu
from ..pipeline import run_pipeline


def handle_run(args, cfg: dict) -> None:
    auto_cpu = False
    if args.device is None and detect_gpu().available is False:
        auto_cpu = True
        cfg = cfg.copy()
        cfg["audio"] = {**cfg.get("audio", {}), **cfg.get("profiles", {}).get("cpu_friendly", {}).get("audio", {})}
        cfg["asr"] = {**cfg.get("asr", {}), **cfg.get("profiles", {}).get("cpu_friendly", {}).get("asr", {})}
        cfg["output"] = {**cfg.get("output", {}), **cfg.get("profiles", {}).get("cpu_friendly", {}).get("output", {})}
    audio_cfg = build_audio_cfg(args, cfg)
    input_cfg = build_input_cfg(args, cfg)
    vad_cfg = build_vad_cfg(args, cfg)
    asr_cfg = build_asr_cfg(args, cfg)
    apply_engine_defaults(args, cfg, audio_cfg, asr_cfg)
    output_cfg = build_output_cfg(args, cfg)
    ensure_log_dir(output_cfg.jsonl_log)
    if auto_cpu:
        print("no GPU found; using cpu_friendly profile")
    run_pipeline(
        audio_cfg=audio_cfg,
        input_cfg=input_cfg,
        vad_cfg=vad_cfg,
        asr_cfg=asr_cfg,
        output_cfg=output_cfg,
    )
