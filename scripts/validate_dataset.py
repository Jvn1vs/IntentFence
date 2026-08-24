from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from intentfence.data import (
    C1_REQUIRED_SPLITS,
    audit_partition_integrity,
    audit_split_manifest,
    file_sha256,
)
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
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Optional sealed split manifest whose self-hash, file hashes, and row counts are verified",
    )
    parser.add_argument("--near-threshold", type=float, default=0.92)
    parser.add_argument("--skip-near-duplicates", action="store_true")
    parser.add_argument("--input-mode", choices=("text", "context", "action"), default="action")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/data_pipeline.yaml"),
        help="C1 data policy containing the action-evidence allowlists",
    )
    args = parser.parse_args()
    if args.output and args.output.exists():
        raise FileExistsError(f"Refusing to overwrite integrity report: {args.output}")
    if not args.config.is_file():
        raise FileNotFoundError(f"Data policy config is missing: {args.config}")

    input_paths: dict[str, Path] = {}
    for expected_split, path in args.input:
        if expected_split in input_paths:
            raise ValueError(f"Duplicate --input role: {expected_split}")
        input_paths[expected_split] = path

    manifest_errors = (
        audit_split_manifest(
            args.manifest,
            expected_splits=C1_REQUIRED_SPLITS,
            supplied_paths=input_paths,
            allow_subset_supplied_paths=True,
        )
        if args.manifest
        else []
    )
    if manifest_errors:
        payload = {
            "status": "failed",
            "errors": manifest_errors,
            "warnings": [],
            "summary": {},
        }
        rendered = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        print(rendered, end="")
        raise SystemExit(1)

    supplied_splits = set(input_paths)
    require_action = supplied_splits if args.input_mode == "action" else set()
    action_policy = None
    if args.input_mode == "action":
        with args.config.open(encoding="utf-8") as handle:
            config = yaml.safe_load(handle)
        if not isinstance(config, dict) or not isinstance(
            config.get("action_evidence_policy"), dict
        ):
            raise ValueError(f"Action evidence policy is missing or invalid: {args.config}")
        action_policy = config["action_evidence_policy"]

    samples = []
    input_evidence: dict[str, dict[str, Any]] = {}
    for expected_split, path in input_paths.items():
        rows = read_jsonl(path)
        if not rows:
            raise ValueError(f"Input split is empty: {expected_split}={path}")
        for sample in rows:
            if sample.split != expected_split:
                raise ValueError(
                    f"{sample.sample_id} declares split={sample.split!r}; expected {expected_split!r}"
                )
            samples.append(sample)
        input_evidence[expected_split] = {
            "path": str(path.resolve()),
            "rows": len(rows),
            "sha256": file_sha256(path),
        }

    report = audit_partition_integrity(
        samples,
        near_threshold=args.near_threshold,
        check_near_duplicates=not args.skip_near_duplicates,
        require_action_splits=require_action,
        action_policy=action_policy,
    )
    errors = report.errors
    payload = {
        "status": "failed" if errors else "passed",
        "errors": errors,
        "warnings": report.warnings,
        "summary": report.summary,
        "input_mode": args.input_mode,
        "inputs": input_evidence,
        "near_threshold": args.near_threshold,
        "near_duplicate_check_performed": not args.skip_near_duplicates,
        "config": {
            "path": str(args.config.resolve()),
            "file_sha256": file_sha256(args.config),
        },
        "manifest": (
            {
                "path": str(args.manifest.resolve()),
                "file_sha256": file_sha256(args.manifest),
                "sealed_sha256": json.loads(args.manifest.read_text(encoding="utf-8")).get(
                    "sha256"
                ),
            }
            if args.manifest
            else None
        ),
    }
    rendered = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.output and not errors:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
