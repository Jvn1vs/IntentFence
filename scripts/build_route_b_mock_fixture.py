from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from intentfence.route_b import build_mock_catalog_records
from intentfence.schema import write_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a Route B framework fixture; output is never training-authorized"
    )
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trace-output", type=Path, required=True)
    args = parser.parse_args()
    for path in (args.output, args.trace_output):
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite fixture artifact: {path}")
    catalog = yaml.safe_load(args.catalog.read_text(encoding="utf-8"))
    if not isinstance(catalog, dict):
        raise ValueError("catalog must contain a mapping")
    records, traces = build_mock_catalog_records(catalog)
    write_jsonl(records, args.output)
    args.trace_output.parent.mkdir(parents=True, exist_ok=True)
    args.trace_output.write_text(
        "".join(json.dumps(trace, ensure_ascii=False, sort_keys=True) + "\n" for trace in traces),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "framework_fixture_not_training_data",
                "records": len(records),
                "traces": len(traces),
                "output": str(args.output),
                "trace_output": str(args.trace_output),
                "external_side_effects": False,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
