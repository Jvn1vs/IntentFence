from __future__ import annotations

import argparse
import json
from pathlib import Path

from intentfence.c2b_config import validate_c2b_config


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a frozen C2b Base configuration")
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = validate_c2b_config(args.config)
    except (OSError, TypeError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(
        json.dumps(
            {
                "status": "c2b_config_validated",
                "run_name": payload["run_name"],
                "seed": payload["seed"],
                "input_mode": payload["input_mode"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
