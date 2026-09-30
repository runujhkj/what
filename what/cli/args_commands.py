import argparse


def add_service_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--sse-path", default=None)
    parser.add_argument("--ws-path", default=None)
    parser.add_argument("--http-path", default=None)
    parser.add_argument("--pair-path", default=None)
    parser.add_argument("--mdns-name", default=None)
    parser.add_argument("--no-mdns", action="store_true")
    parser.add_argument("--advertise-host", default=None)
    parser.add_argument("--max-clients", type=int, default=None)
    parser.add_argument("--files", nargs="*")
    parser.add_argument("--test-error", action="store_true")
    parser.add_argument("--tune", action="store_true")
    parser.add_argument("--battery", action="store_true")
    parser.add_argument("--battery-models", default=None)


def add_client_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--pair", default=None)
    parser.add_argument("-k", "--session-key", default=None)
    parser.add_argument("session_key_pos", nargs="?", default=None, help="session key")
    parser.add_argument("--local", action="store_true", help="use local pairing (no session key)")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--ws-path", default=None)
    parser.add_argument("--transport", default=None, choices=["pcm", "opus"])
    parser.add_argument("--client-id", default=None)
    parser.add_argument("--captions-on", action="store_true", default=None)
    parser.add_argument("--display-mode", default=None, choices=["delta", "block", "line"])
    parser.add_argument("--block-clear", action="store_true")
    parser.add_argument("--no-block-clear", action="store_true")
    parser.add_argument("--normalize", action="store_true")
    parser.add_argument("--no-normalize", action="store_true")
    parser.add_argument("--transcript-prefix", default=None, help="prefix transcript lines for parsing")
    parser.add_argument("--event-prefix", default=None, help="prefix JSON events for parsing")


def add_view_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--sse-url", default=None)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--sse-path", default=None)
    parser.add_argument("--client-id", default=None)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--raw", action="store_true")
    parser.add_argument("--display-mode", default="delta", choices=["delta", "block", "line"])
    parser.add_argument("--block-clear", action="store_true")
    parser.add_argument("--no-block-clear", action="store_true")
    parser.add_argument("--normalize", action="store_true")
    parser.add_argument("--no-normalize", action="store_true")


def add_pair_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-k", "--session-key", required=True)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--pair-path", default=None)


def add_log_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--history", type=int, default=None)
    parser.add_argument("--last", action="store_true")
    parser.add_argument("--id", type=int, default=None)


def add_session_args(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="session_command")
    transcript = sub.add_parser("transcript", help="write transcript.txt for a session folder")
    transcript.add_argument("session_dir")
    pack = sub.add_parser("pack", help="write transcript.txt and <session_id>.what for a session folder")
    pack.add_argument("session_dir")
    pack.add_argument("--copy-to", default=None, help="also copy the .what file here")
    unpack = sub.add_parser("unpack", help="restore a .what file into the logs folder")
    unpack.add_argument("archive")
    unpack.add_argument("--logs-dir", default=None, help="default: WHAT_JSONL_DIR or ./logs")
    for p in (transcript, pack, unpack):
        p.add_argument("--json", action="store_true", help="print a JSON result line")


def add_controller_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--service-host", default=None)
    parser.add_argument("--service-port", type=int, default=None)
    parser.add_argument("--config", default=None)
    parser.add_argument("--settings-path", default=None)


def add_control_client_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--base-url", default=None)
    parser.add_argument("action", choices=["status", "gpu", "start", "stop", "apply"])
    parser.add_argument("--profile", default=None)
    parser.add_argument("--engine", choices=["auto", "faster_whisper", "whisperkit", "whisper_cpp"], default=None)
    parser.add_argument("--device", default=None)
    parser.add_argument("--device-index", type=int, default=None)
    parser.add_argument("--compute-type", default=None)
    parser.add_argument("--model-size", default=None)
    parser.add_argument("--beam-size", type=int, default=None)
    parser.add_argument("--language", default=None)


def add_start_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--service-host", default=None)
    parser.add_argument("--service-port", type=int, default=None)
    parser.add_argument("--health-timeout", type=float, default=8.0)
    parser.add_argument(
        "--force-service",
        action="store_true",
        help="always start a new service process (do not reuse existing service)",
    )
    parser.add_argument(
        "--transcript-prefix",
        default=None,
        help="prefix transcript lines for parsing",
    )
    parser.add_argument(
        "--event-prefix",
        default=None,
        help="prefix JSON events for parsing",
    )


def add_gui_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--control-host", default=None)
    parser.add_argument("--control-port", type=int, default=None)
    parser.add_argument("--service-host", default=None)
    parser.add_argument("--service-port", type=int, default=None)
    parser.add_argument("--npm-bin", default=None)
    parser.add_argument("--gui-dir", default=None)
