from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from intentfence.data import file_sha256
from intentfence.schema import read_jsonl, write_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge user-produced canonical JSONL files")
    parser.add_argument("--input", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report_path = args.report or args.output.with_suffix(".merge.json")
    if args.output.exists() or report_path.exists():
        raise FileExistsError("Refusing to overwrite merge output or report")
    if args.output.resolve() in {path.resolve() for path in args.input}:
        raise ValueError("Merge output cannot overwrite an input path")
    samples = []
    seen: set[str] = set()
    input_evidence = []
    for path in args.input:
        rows = read_jsonl(path)
        if not rows:
            raise ValueError(f"Merge input is empty: {path}")
        input_evidence.append(
            {"path": str(path), "rows": len(rows), "sha256": file_sha256(path)}
        )
        for sample in rows:
            if sample.sample_id in seen:
                raise ValueError(f"duplicate sample_id across inputs: {sample.sample_id}")
            seen.add(sample.sample_id)
            samples.append(sample)
    write_jsonl(samples, args.output)
    report = {
        "schema_version": 1,
        "status": "merged_unverified",
        "inputs": input_evidence,
        "output": str(args.output),
        "output_sha256": file_sha256(args.output),
        "rows": len(samples),
        "sources": dict(sorted(Counter(sample.source for sample in samples).items())),
        "risk_labels": dict(sorted(Counter(sample.risk_label for sample in samples).items())),
        "human_verified": sum(sample.human_verified for sample in samples),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
