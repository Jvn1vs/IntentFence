from __future__ import annotations

import argparse
import json
from pathlib import Path

from intentfence.route_b_ai_training import build_ai_training_readiness


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build fail-closed readiness for owner-run AI-reviewed engineering training; "
            "failed AI quality gates remain visible and require owner risk acceptance"
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/route_b_ai_training_protocol.yaml"),
    )
    parser.add_argument(
        "--protocol-document",
        type=Path,
        default=Path("docs/route_b_ai_training_protocol.md"),
    )
    parser.add_argument(
        "--protocol-lock",
        type=Path,
        default=Path("configs/route_b_ai_training_protocol_lock.json"),
    )
    parser.add_argument(
        "--integrity-policy",
        type=Path,
        help="Data-construction policy bound to the existing integrity report",
    )
    parser.add_argument(
        "--ai-review-policy",
        type=Path,
        help="Historical AI-review policy used to replay the submitted package",
    )
    parser.add_argument("--candidate-manifest", type=Path, required=True)
    parser.add_argument("--integrity-report", type=Path, required=True)
    parser.add_argument("--ai-review-analysis", type=Path, required=True)
    parser.add_argument("--ai-review-manifest", type=Path, required=True)
    parser.add_argument("--audit-manifest", type=Path, required=True)
    parser.add_argument("--public-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(
            f"Refusing to overwrite AI engineering readiness report: {args.output}"
        )
    report = build_ai_training_readiness(
        policy_path=args.config,
        protocol_document=args.protocol_document,
        protocol_lock=args.protocol_lock,
        candidate_manifest=args.candidate_manifest,
        integrity_report=args.integrity_report,
        ai_review_analysis=args.ai_review_analysis,
        ai_review_manifest=args.ai_review_manifest,
        audit_manifest=args.audit_manifest,
        public_report=args.public_report,
        integrity_policy_path=args.integrity_policy,
        ai_review_policy_path=args.ai_review_policy,
    )
    rendered = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return int(not report["engineering_training_eligible"])


if __name__ == "__main__":
    raise SystemExit(main())
