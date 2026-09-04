from __future__ import annotations

import argparse
import json
from pathlib import Path

from intentfence.run_manifest import record_actual_cost


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Record the billed CNY cost after a completed IntentFence run"
    )
    parser.add_argument("--run-manifest", type=Path, required=True)
    parser.add_argument("--cost-cny", type=float, required=True)
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace an existing cost record explicitly.",
    )
    args = parser.parse_args()
    record_actual_cost(args.run_manifest, args.cost_cny, replace=args.replace)
    print(
        json.dumps(
            {
                "status": "run_cost_recorded",
                "run_manifest": str(args.run_manifest),
                "actual_cost_cny": args.cost_cny,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
