from __future__ import annotations

import argparse
import json
from pathlib import Path

from intentfence.data import (
    dataset_summary,
    deduplicate_samples,
    group_aware_split,
    write_split_dataset,
)
from intentfence.schema import read_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Deduplicate and build template-group isolated splits")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--near-threshold", type=float, default=0.92)
    args = parser.parse_args()
    samples = read_jsonl(args.input)
    dedup = deduplicate_samples(samples, near_threshold=args.near_threshold)
    assigned, manifest = group_aware_split(dedup.kept, seed=args.seed)
    manifest["input_summary"] = dataset_summary(samples)
    manifest["deduplication"] = {
        "kept": len(dedup.kept),
        "exact_duplicates": dedup.exact_duplicates,
        "near_duplicates": dedup.near_duplicates,
        "near_threshold": args.near_threshold,
    }
    write_split_dataset(assigned, manifest, args.output_dir)
    print(json.dumps(manifest["counts"], indent=2))


if __name__ == "__main__":
    main()
