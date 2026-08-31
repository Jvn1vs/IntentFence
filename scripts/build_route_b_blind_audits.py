from __future__ import annotations

import argparse
import json
from pathlib import Path

from intentfence.route_b_audit import build_blind_audit_package


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build two independently ordered, seed-label-blinded Route B audit packages"
    )
    parser.add_argument("--input", action="append", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--risk-rows", type=int, default=400)
    parser.add_argument("--alignment-rows", type=int, default=400)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--review-mode",
        choices=("independent_human_blind", "dual_ai_engineering"),
        default="independent_human_blind",
        help="Bind the package to human signoff or the dual-AI engineering route.",
    )
    args = parser.parse_args()
    result = build_blind_audit_package(
        args.input,
        args.output_dir,
        risk_rows=args.risk_rows,
        alignment_rows=args.alignment_rows,
        seed=args.seed,
        review_mode=args.review_mode,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
