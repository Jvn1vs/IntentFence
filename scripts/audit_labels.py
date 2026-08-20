from __future__ import annotations

import argparse
import csv
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
    strata: dict[tuple[str, str], list] = defaultdict(list)
    for sample in samples:
        strata[(sample.source, sample.risk_label)].append(sample)
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
                "risk_label",
                "alignment_label",
                "user_goal",
                "untrusted_content",
                "proposed_action",
                "audit_status",
                "new_risk_label",
                "new_alignment_label",
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
                notes="",
                reviewer="",
                reviewed_at="",
            )
            writer.writerow({key: row.get(key, "") for key in writer.fieldnames})
    print(f"Wrote {len(selected)} audit rows to {args.output}")


if __name__ == "__main__":
    main()
