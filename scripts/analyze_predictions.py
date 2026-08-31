from __future__ import annotations

import argparse
import json
from pathlib import Path

from intentfence.evaluation import (
    build_prediction_report,
    load_prediction_jsonl,
    prediction_file_provenance,
)


def render_markdown(report: dict) -> str:
    identity = report["identity"]
    overall = report["overall"]
    metrics = overall["metrics"]
    operating_point = metrics["operating_point"]
    lines = [
        "# Prediction analysis report",
        "",
        f"Status: **{report['status']}**",
        "",
        f"- Split: `{identity['split']}`",
        f"- Backend: `{identity['backend']}`",
        f"- Revision: `{identity['revision']}`",
        f"- Threshold: `{overall['attack_threshold']}` (source: `{overall['threshold_source']}`)",
        "",
        "## Overall",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Samples | {overall['sample_count']} |",
        f"| Accuracy | {metrics['accuracy']} |",
        f"| Macro-F1 | {metrics['macro_f1']} |",
        f"| Benign FPR | {operating_point['fpr']} |",
        f"| Attack TPR | {operating_point['tpr']} |",
        f"| Attack AUROC | {metrics.get('attack_auroc', 'n/a')} |",
        f"| Attack AUPRC | {metrics.get('attack_auprc', 'n/a')} |",
        f"| ECE | {metrics['ece']} |",
        f"| Brier | {metrics['brier']} |",
        f"| NLL | {metrics['nll']} |",
        "",
        "## Groups",
        "",
    ]
    for field, groups in report["groups"].items():
        lines.extend(
            [
                f"### `{field}`",
                "",
                "| Group | N | Accuracy | Macro-F1 | FPR | TPR |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for value, summary in groups.items():
            group_metrics = summary["metrics"]
            group_point = group_metrics["operating_point"]
            lines.append(
                f"| `{value}` | {summary['sample_count']} | {group_metrics['accuracy']} | "
                f"{group_metrics['macro_f1']} | {group_point['fpr']} | {group_point['tpr']} |"
            )
        lines.append("")
    errors = report["error_analysis"]
    lines.extend(
        [
            "## Error analysis",
            "",
            f"- False negatives: {errors['counts']['false_negatives']}",
            f"- False positives: {errors['counts']['false_positives']}",
            f"- Misclassified: {errors['counts']['misclassified']}",
            "",
            "Only sample identifiers and non-content metadata are listed; raw untrusted content is not copied into this report.",
            "",
            "## Limitations",
            "",
        ]
    )
    lines.extend(f"- {limitation}" for limitation in report["limitations"])
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze supplied frozen prediction JSONL")
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    parser.add_argument("--expected-split")
    parser.add_argument("--attack-threshold", type=float, required=True)
    parser.add_argument("--bootstrap-resamples", type=int, default=10_000)
    parser.add_argument("--confidence-level", type=float, default=0.95)
    parser.add_argument("--bootstrap-seed", type=int, default=42)
    parser.add_argument("--max-error-items", type=int, default=25)
    args = parser.parse_args()
    if args.output_json.resolve() == args.output_markdown.resolve():
        raise ValueError("JSON and Markdown outputs must be different files")
    existing = [path for path in (args.output_json, args.output_markdown) if path.exists()]
    if existing:
        raise FileExistsError(f"refusing to overwrite analysis outputs: {existing}")
    rows = load_prediction_jsonl(args.predictions, expected_split=args.expected_split)
    report = build_prediction_report(
        rows,
        attack_threshold=args.attack_threshold,
        max_error_items=args.max_error_items,
        bootstrap_resamples=args.bootstrap_resamples,
        confidence_level=args.confidence_level,
        bootstrap_seed=args.bootstrap_seed,
    )
    report["provenance"] = prediction_file_provenance(args.predictions)
    report["parameters"] = {
        "attack_threshold": args.attack_threshold,
        "bootstrap_resamples": args.bootstrap_resamples,
        "confidence_level": args.confidence_level,
        "bootstrap_seed": args.bootstrap_seed,
        "max_error_items": args.max_error_items,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.output_markdown.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"status": report["status"], "samples": len(rows)}, indent=2))


if __name__ == "__main__":
    main()
