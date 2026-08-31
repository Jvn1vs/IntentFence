from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from intentfence.data import file_sha256
from intentfence.statistics import summarize_seed_metrics


def _load_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    runs = payload.get("runs")
    if not isinstance(runs, list) or not runs:
        raise ValueError("input must contain a non-empty runs list")
    return payload


def summarize_runs(payload: dict[str, Any], *, source_sha256: str) -> dict[str, Any]:
    runs = payload["runs"]
    values: dict[tuple[str, str], dict[int, float]] = defaultdict(dict)
    for index, run in enumerate(runs):
        if not isinstance(run, dict):
            raise ValueError(f"runs[{index}] must be an object")
        variant = str(run.get("variant", "")).strip()
        seed = run.get("seed")
        metrics = run.get("metrics")
        if not variant:
            raise ValueError(f"runs[{index}] variant must be non-empty")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError(f"runs[{index}] seed must be an integer")
        if not isinstance(metrics, dict) or not metrics:
            raise ValueError(f"runs[{index}] metrics must be a non-empty object")
        for metric_name, value in metrics.items():
            name = str(metric_name).strip()
            if not name:
                raise ValueError(f"runs[{index}] contains an empty metric name")
            numeric_value = float(value)
            if not np.isfinite(numeric_value):
                raise ValueError(f"runs[{index}] metric {name} must be finite")
            key = (variant, name)
            if seed in values[key]:
                raise ValueError(f"duplicate variant/seed: {variant!r}/{seed}")
            values[key][seed] = numeric_value

    summaries: dict[str, dict[str, Any]] = {}
    for (variant, metric_name), seed_values in sorted(values.items()):
        summaries.setdefault(variant, {})[metric_name] = summarize_seed_metrics(
            seed_values, metric_name=metric_name
        )
    return {
        "schema_version": 1,
        "status": "summary_only",
        "source_sha256": source_sha256,
        "protocol_version": payload.get("protocol_version"),
        "variants": summaries,
        "limitations": [
            "Cross-seed summaries do not replace paired per-sample bootstrap intervals.",
            "No final-test or calibration data are created or modified by this command.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize scalar metrics across explicitly supplied training seeds"
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite seed summary: {args.output}")
    payload = _load_payload(args.input)
    report = summarize_runs(payload, source_sha256=file_sha256(args.input))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
