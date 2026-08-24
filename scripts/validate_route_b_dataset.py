from __future__ import annotations

import argparse
from pathlib import Path

from intentfence.data import audit_partition_integrity
from intentfence.route_b import (
    load_route_b_policy,
    render_route_b_report,
    validate_route_b_samples,
)
from intentfence.schema import read_jsonl


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Route B v2 structure without fitting any learned parameters"
    )
    parser.add_argument(
        "--input",
        type=Path,
        action="append",
        required=True,
        help="Candidate JSONL; repeat to validate multiple roles together",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/route_b_data_protocol.yaml"),
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--near-threshold", type=float, default=0.92)
    parser.add_argument("--skip-near-duplicates", action="store_true")
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="Also fail while protocol, sample-size, audit, or authorization blockers remain",
    )
    args = parser.parse_args()
    if args.output and args.output.exists():
        raise FileExistsError(f"Refusing to overwrite Route B report: {args.output}")
    samples = [row for path in args.input for row in read_jsonl(path)]
    report = validate_route_b_samples(samples, load_route_b_policy(args.config))
    integrity = audit_partition_integrity(
        samples,
        near_threshold=args.near_threshold,
        check_near_duplicates=False,
    )
    report["errors"].extend(
        f"partition_integrity: {error}" for error in integrity.errors
    )
    report["warnings"].extend(integrity.warnings)
    report["summary"]["partition_integrity"] = integrity.summary
    if not args.skip_near_duplicates:
        representatives: dict[tuple[str, str, str, str], object] = {}
        for row in samples:
            key = (
                str(row.split),
                row.template_group,
                row.risk_label,
                str(row.task_alignment_label),
            )
            representatives.setdefault(key, row)
        near_integrity = audit_partition_integrity(
            representatives.values(),
            near_threshold=args.near_threshold,
            check_near_duplicates=True,
        )
        report["errors"].extend(
            f"template_representative_integrity: {error}"
            for error in near_integrity.errors
        )
        report["summary"]["template_representative_near_integrity"] = {
            "representatives": len(representatives),
            **near_integrity.summary,
        }
    report["near_threshold"] = args.near_threshold
    report["near_duplicate_check_performed"] = not args.skip_near_duplicates
    report["near_duplicate_scope"] = "one representative per split/template/risk/alignment"
    if report["errors"]:
        report["status"] = "failed"
    rendered = render_route_b_report(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if report["errors"] or (args.require_ready and report["readiness_blockers"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
