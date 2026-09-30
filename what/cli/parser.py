import argparse

from .args_commands import (
    add_controller_args,
    add_control_client_args,
    add_client_args,
    add_gui_args,
    add_log_args,
    add_pair_args,
    add_service_args,
    add_start_args,
    add_view_args,
)
from .args_common import (
    add_asr_args,
    add_audio_tuning_args,
    add_config_args,
    add_input_args,
    add_output_args,
    add_vad_args,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="what")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run")
    add_config_args(run_parser)
    add_input_args(run_parser)
    add_asr_args(run_parser)
    add_audio_tuning_args(run_parser)
    add_vad_args(run_parser)
    add_output_args(run_parser)

    service_parser = subparsers.add_parser("service")
    add_config_args(service_parser)
    add_asr_args(service_parser)
    add_audio_tuning_args(service_parser)
    add_vad_args(service_parser)
    add_output_args(service_parser)
    add_service_args(service_parser)

    client_parser = subparsers.add_parser("client")
    add_config_args(client_parser)
    add_input_args(client_parser)
    add_audio_tuning_args(client_parser)
    add_client_args(client_parser)

    view_parser = subparsers.add_parser("view")
    add_view_args(view_parser)

    pair_parser = subparsers.add_parser("pair")
    # main() calls load_cfg(args.config, args.preset, args.profile) before dispatching
    # pair, and handle_pair reads cfg["service"] defaults, so pair needs the config args
    # too -- without them `what pair -k KEY` raised AttributeError on args.config.
    add_config_args(pair_parser)
    add_pair_args(pair_parser)

    log_parser = subparsers.add_parser("log")
    add_log_args(log_parser)

    control_parser = subparsers.add_parser("control")
    add_controller_args(control_parser)

    control_client_parser = subparsers.add_parser("control-client")
    add_control_client_args(control_client_parser)

    start_parser = subparsers.add_parser("start")
    add_config_args(start_parser)
    add_input_args(start_parser)
    add_audio_tuning_args(start_parser)
    add_asr_args(start_parser)
    add_vad_args(start_parser)
    add_output_args(start_parser)
    add_start_args(start_parser)

    gui_parser = subparsers.add_parser("gui")
    add_gui_args(gui_parser)

    return parser
