from __future__ import annotations

import argparse
import json
from pathlib import Path

from intentfence.data import audit_partition_integrity
from intentfence.schema import read_jsonl


def _input_spec(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("input must be SPLIT=PATH")
    split, raw_path = value.split("=", maxsplit=1)
    return split, Path(raw_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit user-produced canonical split files")
    parser.add_argument("--input", action="append", type=_input_spec, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--near-threshold", type=float, default=0.92)
    parser.add_argument("--skip-near-duplicates", action="store_true")
    parser.add_argument("--input-mode", choices=("text", "context", "action"), default="action")
    args = parser.parse_args()

    samples = []
    for expected_split, path in args.input:
        for sample in read_jsonl(path):
            if sample.split != expected_split:
                raise ValueError(
                    f"{sample.sample_id} declares split={sample.split!r}; expected {expected_split!r}"
                )
            samples.append(sample)

    require_action = (
        {"train", "validation", "calibration"} if args.input_mode == "action" else set()
    )
    report = audit_partition_integrity(
        samples,
        near_threshold=args.near_threshold,
        check_near_duplicates=not args.skip_near_duplicates,
        require_action_splits=require_action,
    )
    payload = {
        "status": "failed" if report.errors else "passed",
        "errors": report.errors,
        "warnings": report.warnings,
        "summary": report.summary,
    }
    rendered = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if report.errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
