import json
import sys
from pathlib import Path

from ..env import get_env
from ..session_files import SessionFileError, pack_session, unpack_session, write_transcript


def _default_logs_dir() -> Path:
    # Same resolution as the service (build_output_cfg) and controller (resolve_log_root).
    return Path(get_env("WHAT_JSONL_DIR") or "logs")


def handle_session(args) -> None:
    try:
        if args.session_command == "transcript":
            result = {"ok": True, "path": str(write_transcript(Path(args.session_dir)))}
        elif args.session_command == "pack":
            copy_to = Path(args.copy_to) if args.copy_to else None
            result = {"ok": True, "path": str(pack_session(Path(args.session_dir), copy_to))}
        elif args.session_command == "unpack":
            logs_dir = Path(args.logs_dir) if args.logs_dir else _default_logs_dir()
            session_dir = unpack_session(Path(args.archive), logs_dir)
            result = {"ok": True, "session_id": session_dir.name, "session_dir": str(session_dir)}
        else:
            print("use: what session transcript|pack|unpack (see --help)", file=sys.stderr)
            sys.exit(2)
    except (SessionFileError, OSError) as exc:
        result = {"ok": False, "error": str(exc)}
    if args.json:
        print(json.dumps(result))
    elif result["ok"]:
        print(result.get("session_dir") or result["path"])
    else:
        print(f"error: {result['error']}", file=sys.stderr)
    if not result["ok"]:
        sys.exit(1)
