from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from summarize_label_audit import summarize, validate_audit_key

from intentfence.data import file_sha256
from intentfence.schema import IntentSample, read_jsonl, write_jsonl


def apply_audit(
    samples: list[IntentSample], rows: list[dict[str, str]], minimum_rows: int
) -> tuple[list[IntentSample], dict[str, Any]]:
    audit_report = summarize(rows, minimum_rows)
    if audit_report["errors"]:
        raise ValueError("Audit sheet failed validation: " + "; ".join(audit_report["errors"]))
    by_id: dict[str, dict[str, str]] = {}
    for row in rows:
        sample_id = row.get("sample_id", "").strip()
        if not row.get("audit_status", "").strip():
            continue
        if sample_id in by_id:
            raise ValueError(f"Duplicate completed audit row: {sample_id}")
        by_id[sample_id] = row

    output: list[IntentSample] = []
    applied = Counter()
    known_ids = {sample.sample_id for sample in samples}
    unknown = sorted(set(by_id) - known_ids)
    if unknown:
        raise ValueError(f"Audit contains unknown sample IDs: {unknown[:10]}")

    for sample in samples:
        row = by_id.get(sample.sample_id)
        if row is None:
            output.append(sample)
            applied["unaudited_retained"] += 1
            continue
        status = row["audit_status"].strip().casefold()
        if status == "ambiguous":
            applied["ambiguous_excluded"] += 1
            continue
        if status == "correct":
            output.append(sample.model_copy(update={"human_verified": True}))
            applied["confirmed"] += 1
            continue
        corrected = sample.model_copy(
            update={
                "risk_label": row["new_risk_label"].strip(),
                "alignment_label": int(row["new_alignment_label"]),
                "severity": int(row["new_severity"]),
                "human_verified": True,
                "label_provenance": "user_audit_correction",
            }
        )
        corrected = IntentSample.model_validate(corrected.model_dump())
        output.append(corrected)
        applied["corrected"] += 1

    return output, {**audit_report, "application_counts": dict(sorted(applied.items()))}


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply a validated project-owner label audit")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--audit-key", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--minimum-rows", type=int, default=200)
    args = parser.parse_args()
    if args.output.exists() or args.report.exists():
        raise FileExistsError("Refusing to overwrite audit output or report")
    with args.audit.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    key_path = args.audit_key or args.audit.with_suffix(".audit_key.json")
    key, key_errors = validate_audit_key(
        key_path,
        args.audit,
        rows,
        expected_input=args.input,
    )
    if key_errors:
        raise ValueError("Audit key validation failed: " + "; ".join(key_errors))
    if not isinstance(key.get("input"), str) or Path(key["input"]).resolve() != args.input.resolve():
        raise ValueError("Audit key input path does not match --input")
    if key.get("input_sha256") != file_sha256(args.input):
        raise ValueError("Audit key input hash does not match --input")
    samples, report = apply_audit(read_jsonl(args.input), rows, args.minimum_rows)
    write_jsonl(samples, args.output)
    report.update(
        {
            "input": str(args.input),
            "input_sha256": file_sha256(args.input),
            "audit": str(args.audit),
            "audit_sha256": file_sha256(args.audit),
            "audit_key": str(key_path),
            "audit_key_sha256": file_sha256(key_path),
            "output": str(args.output),
            "output_sha256": file_sha256(args.output),
        }
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["application_counts"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
