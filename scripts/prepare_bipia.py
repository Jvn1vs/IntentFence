from __future__ import annotations

import argparse
import json
from pathlib import Path

from _prepare import convert_file


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Strictly normalize an official BIPIA builder export or clean context file"
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--kind", choices=("generated", "clean"), default="generated")
    parser.add_argument(
        "--task-name",
        help="Required for clean context files because they do not carry the BIPIA task name",
    )
    parser.add_argument("--allow-skips", action="store_true")
    args = parser.parse_args()
    if args.kind == "clean" and not args.task_name:
        parser.error("--task-name is required when --kind clean")
    report = convert_file(
        args.input,
        args.output,
        profile_name=f"bipia_{args.kind}_v1",
        allow_skips=args.allow_skips,
        scenario_override=args.task_name,
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
