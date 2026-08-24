from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from summarize_label_audit import (
    AUDIT_REQUIRED_GROUPING,
    AUDIT_SELECTION_ALGORITHM,
    AUDIT_SELECTION_ALGORITHM_VERSION,
    AUDIT_SELECTION_SEED,
    IMMUTABLE_AUDIT_FIELDS,
    audit_row_digest,
    deterministic_stratified_selection,
)

from intentfence.data import file_sha256
from intentfence.schema import read_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a stratified manual label-audit sheet")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--size", type=int, default=200)
    parser.add_argument("--seed", type=int, default=AUDIT_SELECTION_SEED)
    args = parser.parse_args()
    key_path = args.output.with_suffix(".audit_key.json")
    if args.output.exists() or key_path.exists():
        raise FileExistsError("Refusing to overwrite an existing audit sheet or audit key")
    if args.seed != AUDIT_SELECTION_SEED:
        raise ValueError(
            f"--seed must match the frozen C1 audit seed {AUDIT_SELECTION_SEED}"
        )
    samples = read_jsonl(args.input)
    selected = deterministic_stratified_selection(
        samples,
        requested_size=args.size,
        seed=args.seed,
        grouping=AUDIT_REQUIRED_GROUPING,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "sample_id",
                "source",
                "scenario",
                "adapter_profile",
                "action_provenance",
                "risk_label",
                "alignment_label",
                "severity",
                "user_goal",
                "untrusted_content",
                "proposed_action",
                "audit_status",
                "new_risk_label",
                "new_alignment_label",
                "new_severity",
                "notes",
                "reviewer",
                "reviewed_at",
            ),
        )
        writer.writeheader()
        for sample in selected:
            row = sample.model_dump()
            row.update(
                audit_status="",
                new_risk_label="",
                new_alignment_label="",
                new_severity="",
                notes="",
                reviewer="",
                reviewed_at="",
            )
            writer.writerow({key: row.get(key, "") for key in writer.fieldnames})
    key_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "selection_algorithm": AUDIT_SELECTION_ALGORITHM,
                "selection_algorithm_version": AUDIT_SELECTION_ALGORITHM_VERSION,
                "seed": args.seed,
                "requested_size": args.size,
                "selected": len(selected),
                "required_grouping": list(AUDIT_REQUIRED_GROUPING),
                "input": str(args.input.resolve()),
                "input_sha256": file_sha256(args.input),
                "audit_sheet": str(args.output.resolve()),
                "audit_sheet_initial_sha256": file_sha256(args.output),
                "sample_ids": [sample.sample_id for sample in selected],
                "immutable_fields": list(IMMUTABLE_AUDIT_FIELDS),
                "immutable_row_sha256": {
                    sample.sample_id: audit_row_digest(sample.model_dump(mode="json"))
                    for sample in selected
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(selected)} audit rows to {args.output}")


if __name__ == "__main__":
    main()
