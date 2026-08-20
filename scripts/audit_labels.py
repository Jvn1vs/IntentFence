from __future__ import annotations

import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path

from intentfence.schema import read_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a stratified manual label-audit sheet")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--size", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    samples = read_jsonl(args.input)
    strata: dict[tuple[str, str, str], list] = defaultdict(list)
    for sample in samples:
        strata[(sample.source, sample.risk_label, sample.action_provenance)].append(sample)
    rng = random.Random(args.seed)
    for group in strata.values():
        rng.shuffle(group)
    selected = []
    keys = sorted(strata)
    while len(selected) < min(args.size, len(samples)) and any(strata.values()):
        for key in keys:
            if strata[key] and len(selected) < args.size:
                selected.append(strata[key].pop())
    rng.shuffle(selected)
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
    key_path = args.output.with_suffix(".audit_key.json")
    key_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "seed": args.seed,
                "requested_size": args.size,
                "selected": len(selected),
                "sample_ids": [sample.sample_id for sample in selected],
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
