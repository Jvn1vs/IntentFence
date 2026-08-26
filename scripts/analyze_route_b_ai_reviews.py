from __future__ import annotations

import argparse
import json
from pathlib import Path

from intentfence.route_b_ai_review import analyze_dual_ai_reviews, load_ai_review_policy


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate and analyze two independent AI Route B engineering reviews"
    )
    parser.add_argument("--reviewer-a-risk", type=Path, required=True)
    parser.add_argument("--reviewer-b-risk", type=Path, required=True)
    parser.add_argument("--reviewer-a-alignment", type=Path, required=True)
    parser.add_argument("--reviewer-b-alignment", type=Path, required=True)
    parser.add_argument("--sealed-seed-labels", type=Path, required=True)
    parser.add_argument("--audit-manifest", type=Path, required=True)
    parser.add_argument("--ai-review-manifest", type=Path, required=True)
    parser.add_argument(
        "--config", type=Path, default=Path("configs/route_b_ai_review_protocol.yaml")
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite AI review analysis: {args.output}")
    report = analyze_dual_ai_reviews(
        reviewer_a_risk=args.reviewer_a_risk,
        reviewer_b_risk=args.reviewer_b_risk,
        reviewer_a_alignment=args.reviewer_a_alignment,
        reviewer_b_alignment=args.reviewer_b_alignment,
        sealed_seed_labels=args.sealed_seed_labels,
        audit_manifest=args.audit_manifest,
        ai_review_manifest=args.ai_review_manifest,
        policy=load_ai_review_policy(args.config),
    )
    rendered = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return int(report["status"] != "ai_quality_gates_passed_engineering_only")


if __name__ == "__main__":
    raise SystemExit(main())
