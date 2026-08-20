from __future__ import annotations

import argparse
import json
from pathlib import Path

from _prepare import convert_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Strictly normalize an official NotInject export")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-skips", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            convert_file(
                args.input,
                args.output,
                profile_name="notinject_v1",
                allow_skips=args.allow_skips,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
