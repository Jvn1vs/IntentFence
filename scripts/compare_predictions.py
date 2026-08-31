from __future__ import annotations

import argparse
import json
from pathlib import Path

from intentfence.evaluation import (
    compare_prediction_rows,
    load_prediction_jsonl,
    prediction_file_provenance,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare paired prediction JSONL files at separately frozen thresholds"
    )
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--baseline-threshold", type=float, required=True)
    parser.add_argument("--candidate-threshold", type=float, required=True)
    parser.add_argument("--endpoint", choices=("fpr", "tpr"), required=True)
    parser.add_argument("--expected-split")
    parser.add_argument("--bootstrap-resamples", type=int, default=10_000)
    parser.add_argument("--confidence-level", type=float, default=0.95)
    parser.add_argument("--bootstrap-seed", type=int, default=42)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite comparison output: {args.output}")
    baseline = load_prediction_jsonl(args.baseline, expected_split=args.expected_split)
    candidate = load_prediction_jsonl(args.candidate, expected_split=args.expected_split)
    comparison = compare_prediction_rows(
        baseline,
        candidate,
        baseline_threshold=args.baseline_threshold,
        candidate_threshold=args.candidate_threshold,
        endpoint=args.endpoint,
        n_resamples=args.bootstrap_resamples,
        confidence_level=args.confidence_level,
        bootstrap_seed=args.bootstrap_seed,
    )
    comparison.update(
        {
            "schema_version": 1,
            "status": "analysis_only",
            "claim_scope": "paired_supplied_predictions_only_no_new_model_or_final_test_access",
            "baseline_provenance": prediction_file_provenance(args.baseline),
            "candidate_provenance": prediction_file_provenance(args.candidate),
            "parameters": {
                "bootstrap_resamples": args.bootstrap_resamples,
                "confidence_level": args.confidence_level,
                "bootstrap_seed": args.bootstrap_seed,
            },
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(comparison, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": comparison["status"],
                "endpoint": comparison["endpoint"],
                "paired_samples": comparison["paired_samples"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
