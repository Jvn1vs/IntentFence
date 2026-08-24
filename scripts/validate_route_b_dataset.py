from __future__ import annotations

import argparse
from pathlib import Path

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
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/route_b_data_protocol.yaml"),
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="Also fail while protocol, sample-size, audit, or authorization blockers remain",
    )
    args = parser.parse_args()
    if args.output and args.output.exists():
        raise FileExistsError(f"Refusing to overwrite Route B report: {args.output}")
    report = validate_route_b_samples(
        read_jsonl(args.input),
        load_route_b_policy(args.config),
    )
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

