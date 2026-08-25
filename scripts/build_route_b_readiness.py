from __future__ import annotations

import argparse
import json
from pathlib import Path

from intentfence.route_b_readiness import evaluate_route_b_readiness


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the fail-closed Route B training-readiness report"
    )
    parser.add_argument(
        "--config", type=Path, default=Path("configs/route_b_data_protocol.yaml")
    )
    parser.add_argument(
        "--protocol-document",
        type=Path,
        default=Path("docs/route_b_data_protocol.md"),
    )
    parser.add_argument("--protocol-lock", type=Path)
    parser.add_argument("--candidate-manifest", type=Path, required=True)
    parser.add_argument("--integrity-report", type=Path, required=True)
    parser.add_argument("--audit-analysis", type=Path)
    parser.add_argument("--audit-manifest", type=Path)
    parser.add_argument("--public-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite Route B readiness report: {args.output}")
    report = evaluate_route_b_readiness(
        policy_path=args.config,
        protocol_document=args.protocol_document,
        protocol_lock=args.protocol_lock,
        candidate_manifest=args.candidate_manifest,
        integrity_report=args.integrity_report,
        audit_analysis=args.audit_analysis,
        audit_manifest=args.audit_manifest,
        public_report=args.public_report,
    )
    rendered = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return int(not report["formal_training_authorized"])


if __name__ == "__main__":
    raise SystemExit(main())
