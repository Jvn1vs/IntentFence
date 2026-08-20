from __future__ import annotations

import argparse
import json
from pathlib import Path

from _prepare import convert_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize a NotInject JSON/JSONL export")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-missing-action", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            convert_file(
                args.input,
                args.output,
                source="NotInject",
                default_risk="benign",
                force_benign=True,
                allow_missing_action=args.allow_missing_action,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
