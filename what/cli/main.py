import os
import sys

from .config import load_cfg, validate_language
from .handle_client import handle_client
from .handle_control_client import handle_control_client
from .handle_control import handle_control
from .handle_gui import handle_gui
from .handle_log import handle_log
from .handle_pair import handle_pair
from .handle_run import handle_run
from .handle_start import handle_start
from .handle_service import handle_service
from .handle_view import handle_view
from .parser import build_parser
from ..env import load_env


COMMANDS = {"run", "service", "client", "view", "pair", "log", "control", "control-client", "start", "gui"}


def main() -> None:
    argv = sys.argv[1:]
    command = argv[0] if argv else "run"
    if command not in COMMANDS:
        command = "run"
    if "WHAT_ENV_FILE" not in os.environ:
        if command == "service" and os.path.exists(".env.service"):
            os.environ["WHAT_ENV_FILE"] = ".env.service"
        elif command == "client" and os.path.exists(".env.client"):
            os.environ["WHAT_ENV_FILE"] = ".env.client"
        elif command == "start" and os.path.exists(".env.client"):
            os.environ["WHAT_ENV_FILE"] = ".env.client"
    load_env()
    parser = build_parser()
    if not argv or argv[0] not in COMMANDS:
        argv = ["run"] + argv
    args = parser.parse_args(argv)

    if args.command == "view":
        handle_view(args)
        return

    if args.command == "log":
        handle_log(args)
        return

    if args.command == "control":
        handle_control(args)
        return
    if args.command == "control-client":
        handle_control_client(args)
        return
    if args.command == "gui":
        handle_gui(args)
        return

    cfg = load_cfg(args.config, args.preset, args.profile)

    if args.command == "pair":
        handle_pair(args, cfg)
        return

    if args.command in ("run", "service"):
        validate_language(args.lang, cfg)

    if args.command == "run":
        handle_run(args, cfg)
        return

    if args.command == "service":
        handle_service(args, cfg)
        return

    if args.command == "start":
        handle_start(args, cfg)
        return

    if args.command == "client":
        handle_client(args, cfg)
        return

    parser.print_help()
