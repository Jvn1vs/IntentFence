from __future__ import annotations

import argparse
import json
from pathlib import Path

from _prepare import convert_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize an exported BIPIA JSON/JSONL file")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--allow-missing-action",
        action="store_true",
        help="Keep rows for text/context baselines with NO_ACTION_PROVIDED",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            convert_file(
                args.input,
                args.output,
                source="BIPIA",
                default_risk="instruction_hijacking",
                allow_missing_action=args.allow_missing_action,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
