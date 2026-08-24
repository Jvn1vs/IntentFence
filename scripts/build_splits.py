from __future__ import annotations

import argparse
import json
from pathlib import Path

from intentfence.data import (
    C1_REQUIRED_SPLITS,
    audit_partition_integrity,
    dataset_summary,
    deduplicate_samples,
    file_sha256,
    group_aware_split,
    write_split_dataset,
)
from intentfence.schema import read_jsonl


def _fixed_input_spec(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("fixed input must be SPLIT=PATH")
    split, raw_path = value.split("=", maxsplit=1)
    if split not in {"test_b", "test_c"}:
        raise argparse.ArgumentTypeError("fixed input split must be test_b or test_c")
    return split, Path(raw_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deduplicate and build template-group isolated splits"
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--near-threshold", type=float, default=0.92)
    parser.add_argument(
        "--fixed-input",
        action="append",
        type=_fixed_input_spec,
        default=[],
        help="Canonical fixed external split input as test_b=PATH or test_c=PATH",
    )
    args = parser.parse_args()
    fixed_roles = {split for split, _ in args.fixed_input}
    required_fixed_roles = {"test_b", "test_c"}
    if fixed_roles != required_fixed_roles:
        missing = sorted(required_fixed_roles - fixed_roles)
        unexpected = sorted(fixed_roles - required_fixed_roles)
        details = []
        if missing:
            details.append(f"missing fixed roles: {', '.join(missing)}")
        if unexpected:
            details.append(f"unexpected fixed roles: {', '.join(unexpected)}")
        raise ValueError("C1 split build requires test_b and test_c; " + "; ".join(details))
    samples = read_jsonl(args.input)
    dedup = deduplicate_samples(samples, near_threshold=args.near_threshold)
    assigned, manifest = group_aware_split(dedup.kept, seed=args.seed)
    fixed_samples = []
    fixed_inputs: dict[str, list[dict[str, object]]] = {}
    for expected_split, path in args.fixed_input:
        rows = read_jsonl(path)
        if not rows:
            raise ValueError(f"Fixed split input is empty: {expected_split}={path}")
        for sample in rows:
            if sample.split != expected_split:
                raise ValueError(
                    f"{sample.sample_id} declares split={sample.split!r}; "
                    f"expected fixed split {expected_split!r}"
                )
        fixed_samples.extend(rows)
        fixed_inputs.setdefault(expected_split, []).append(
            {"path": str(path), "rows": len(rows), "sha256": file_sha256(path)}
        )
    combined = [*assigned, *fixed_samples]
    observed_roles = {sample.split for sample in combined}
    required_roles = set(C1_REQUIRED_SPLITS)
    if observed_roles != required_roles:
        missing = sorted(required_roles - observed_roles)
        unexpected = sorted(observed_roles - required_roles, key=str)
        raise ValueError(
            "C1 split build must contain exactly six roles; "
            f"missing={missing}, unexpected={unexpected}"
        )
    prewrite_audit = audit_partition_integrity(combined, check_near_duplicates=False)
    if prewrite_audit.errors:
        raise ValueError("Fixed split integration failed: " + "; ".join(prewrite_audit.errors))
    manifest["input_summary"] = dataset_summary(samples)
    manifest["primary_input"] = {
        "path": str(args.input),
        "rows": len(samples),
        "sha256": file_sha256(args.input),
    }
    manifest["deduplication"] = {
        "kept": len(dedup.kept),
        "exact_duplicates": dedup.exact_duplicates,
        "near_duplicates": dedup.near_duplicates,
        "near_threshold": args.near_threshold,
    }
    manifest["fixed_inputs"] = {key: value for key, value in sorted(fixed_inputs.items())}
    for split in sorted(fixed_inputs):
        rows = [sample for sample in fixed_samples if sample.split == split]
        manifest["counts"][split] = {
            "total": len(rows),
            "by_risk": dataset_summary(rows)["risk_labels"],
        }
    final_manifest = write_split_dataset(
        combined,
        manifest,
        args.output_dir,
        expected_splits=C1_REQUIRED_SPLITS,
    )
    print(json.dumps(final_manifest["counts"], indent=2))


if __name__ == "__main__":
    main()
