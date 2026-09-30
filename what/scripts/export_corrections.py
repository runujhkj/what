import argparse
import json

from ..corrections import export_bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corrections-dir", required=True)
    parser.add_argument("--export-dir", required=True)
    parser.add_argument("--me", default="me")
    parser.add_argument("--instance-id", default="default")
    parser.add_argument("--notes", default="")
    args = parser.parse_args()
    result = export_bundle(
        corrections_dir=args.corrections_dir,
        export_dir=args.export_dir,
        me_speaker_id=args.me,
        instance_id=args.instance_id,
        notes=args.notes,
    )
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
