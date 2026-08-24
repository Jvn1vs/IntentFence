from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _result_spec(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("result must be BASELINE=PATH")
    baseline, raw_path = value.split("=", maxsplit=1)
    if not baseline:
        raise argparse.ArgumentTypeError("baseline name cannot be empty")
    return baseline, Path(raw_path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def aggregate(
    results: list[tuple[str, Path, dict[str, Any]]],
    *,
    expected_baselines: set[str] | None = None,
    expected_tests: set[str] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for baseline, path, result in results:
        test_split = result.get("test_split")
        key = (baseline, str(test_split))
        if key in seen:
            errors.append(f"duplicate baseline/test result: {baseline}/{test_split}")
            continue
        seen.add(key)
        if result.get("threshold_source") != "calibration_only":
            errors.append(f"threshold is not calibration-only: {baseline}/{test_split}")
        test = result.get("test")
        if not isinstance(test, dict):
            errors.append(f"test operating point is missing: {baseline}/{test_split}")
            continue
        rows.append(
            {
                "baseline": baseline,
                "backend": result.get("backend"),
                "revision": result.get("revision"),
                "test_split": test_split,
                "threshold": result.get("threshold"),
                "fpr": test.get("fpr"),
                "tpr": test.get("tpr"),
                "precision": test.get("precision"),
                "fp": test.get("fp"),
                "fn": test.get("fn"),
                "operational_failure": result.get("operational_failure"),
                "result_path": str(path),
                "result_sha256": _sha256(path),
            }
        )
    if expected_baselines is not None and expected_tests is not None:
        expected = {
            (baseline, test) for baseline in expected_baselines for test in expected_tests
        }
        missing = sorted(expected - seen)
        unexpected = sorted(seen - expected)
        if missing:
            errors.append(f"baseline matrix is missing cells: {missing}")
        if unexpected:
            errors.append(f"baseline matrix has unexpected cells: {unexpected}")
    return {
        "schema_version": 1,
        "status": "failed" if errors else "passed",
        "errors": errors,
        "rows": sorted(rows, key=lambda row: (str(row["baseline"]), str(row["test_split"]))),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Frozen baseline result table",
        "",
        f"Status: **{report['status']}**",
        "",
        "| Baseline | Revision | Test | Threshold | FPR | TPR | Precision | FP | FN | Operational failure |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in report["rows"]:
        lines.append(
            f"| {row['baseline']} | `{row['revision']}` | {row['test_split']} | "
            f"{row['threshold']} | {row['fpr']} | {row['tpr']} | {row['precision']} | "
            f"{row['fp']} | {row['fn']} | {row['operational_failure']} |"
        )
    if report["errors"]:
        lines.extend(["", "## Errors", ""])
        lines.extend(f"- {error}" for error in report["errors"])
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aggregate calibration-only frozen baseline evaluations"
    )
    parser.add_argument("--result", action="append", type=_result_spec, required=True)
    parser.add_argument("--expected-baseline", action="append")
    parser.add_argument("--expected-test", action="append")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    args = parser.parse_args()
    if args.output_json == args.output_markdown:
        raise ValueError("Baseline JSON and Markdown outputs must be distinct")
    existing = [path for path in (args.output_json, args.output_markdown) if path.exists()]
    if existing:
        raise FileExistsError(
            "Refusing to overwrite baseline table outputs: " + ", ".join(map(str, existing))
        )
    loaded: list[tuple[str, Path, dict[str, Any]]] = []
    for baseline, path in args.result:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Baseline result must contain an object: {path}")
        loaded.append((baseline, path, payload))
    if bool(args.expected_baseline) != bool(args.expected_test):
        raise ValueError("Use --expected-baseline and --expected-test together")
    report = aggregate(
        loaded,
        expected_baselines=set(args.expected_baseline) if args.expected_baseline else None,
        expected_tests=set(args.expected_test) if args.expected_test else None,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.output_markdown.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"status": report["status"], "rows": len(report["rows"])}, indent=2))
    if report["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
