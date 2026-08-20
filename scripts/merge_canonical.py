from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from intentfence.schema import read_jsonl, write_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge user-produced canonical JSONL files")
    parser.add_argument("--input", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite {args.output}")
    samples = []
    seen: set[str] = set()
    for path in args.input:
        for sample in read_jsonl(path):
            if sample.sample_id in seen:
                raise ValueError(f"duplicate sample_id across inputs: {sample.sample_id}")
            seen.add(sample.sample_id)
            samples.append(sample)
    write_jsonl(samples, args.output)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "rows": len(samples),
                "sources": dict(sorted(Counter(sample.source for sample in samples).items())),
                "risk_labels": dict(
                    sorted(Counter(sample.risk_label for sample in samples).items())
                ),
                "human_verified": sum(sample.human_verified for sample in samples),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
