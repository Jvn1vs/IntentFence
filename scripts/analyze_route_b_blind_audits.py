from __future__ import annotations

import argparse
import json
from pathlib import Path

from intentfence.route_b import load_route_b_policy
from intentfence.route_b_audit_analysis import analyze_blind_audits


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and analyze two blind Route B reviews")
    parser.add_argument("--reviewer-a-risk", type=Path, required=True)
    parser.add_argument("--reviewer-b-risk", type=Path, required=True)
    parser.add_argument("--reviewer-a-alignment", type=Path, required=True)
    parser.add_argument("--reviewer-b-alignment", type=Path, required=True)
    parser.add_argument("--sealed-seed-labels", type=Path, required=True)
    parser.add_argument("--audit-manifest", type=Path, required=True)
    parser.add_argument(
        "--config", type=Path, default=Path("configs/route_b_data_protocol.yaml")
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite Route B audit analysis: {args.output}")
    report = analyze_blind_audits(
        reviewer_a_risk=args.reviewer_a_risk,
        reviewer_b_risk=args.reviewer_b_risk,
        reviewer_a_alignment=args.reviewer_a_alignment,
        reviewer_b_alignment=args.reviewer_b_alignment,
        sealed_seed_labels=args.sealed_seed_labels,
        audit_manifest=args.audit_manifest,
        policy=load_route_b_policy(args.config),
    )
    rendered = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return int(report["status"] in {"invalid_review_package", "quality_gates_failed_revise_corpus"})


if __name__ == "__main__":
    raise SystemExit(main())
