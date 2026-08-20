from __future__ import annotations

import argparse
import json
from pathlib import Path

from intentfence.data import deduplicate_samples
from intentfence.schema import read_jsonl, write_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove exact and high-overlap samples")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--near-threshold", type=float, default=0.92)
    args = parser.parse_args()
    result = deduplicate_samples(read_jsonl(args.input), near_threshold=args.near_threshold)
    write_jsonl(result.kept, args.output)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(
            {
                "kept": len(result.kept),
                "exact_duplicates": result.exact_duplicates,
                "near_duplicates": result.near_duplicates,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
