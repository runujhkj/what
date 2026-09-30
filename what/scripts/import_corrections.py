import argparse
import json

from ..corrections import import_bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--map", default="{}")
    args = parser.parse_args()
    try:
        speaker_map = json.loads(args.map)
    except json.JSONDecodeError:
        speaker_map = {}
    result = import_bundle(
        bundle_path=args.bundle,
        out_dir=args.out_dir,
        speaker_map=speaker_map,
    )
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
