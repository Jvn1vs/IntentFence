from __future__ import annotations

import argparse
import json
from pathlib import Path

from _prepare import convert_file


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Strictly normalize an official InjecAgent test file"
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--attack-kind", choices=("direct-harm", "data-stealing"), required=True)
    parser.add_argument("--allow-skips", action="store_true")
    args = parser.parse_args()
    profile = {
        "direct-harm": "injecagent_direct_harm_v1",
        "data-stealing": "injecagent_data_stealing_v1",
    }[args.attack_kind]
    print(
        json.dumps(
            convert_file(
                args.input,
                args.output,
                profile_name=profile,
                allow_skips=args.allow_skips,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
