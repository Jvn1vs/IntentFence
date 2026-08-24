from __future__ import annotations

import argparse
import json

from intentfence.route_b import precision_table


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Report Wilson precision candidates; this does not freeze Route B sample sizes"
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        action="append",
        default=[],
        help="Candidate benign count; repeat for multiple values",
    )
    parser.add_argument("--target-rate", type=float, default=0.01)
    args = parser.parse_args()
    sample_sizes = args.sample_size or [100, 339, 500, 1000, 2000, 5000]
    payload = {
        "status": "planning_only_not_a_frozen_sample_size",
        "target_rate": args.target_rate,
        "method": "Wilson score interval, nominal 95%",
        "limitations": [
            "row-level binomial precision does not replace cluster-aware design analysis",
            "this table does not address attack-class recall, Macro-F1, or annotation quality",
        ],
        "candidates": precision_table(sample_sizes, target_rate=args.target_rate),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
