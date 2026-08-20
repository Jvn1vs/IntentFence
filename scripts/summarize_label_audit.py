from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ALLOWED_STATUSES = {"correct", "incorrect", "ambiguous"}


def summarize(rows: list[dict[str, str]], minimum_rows: int) -> dict[str, Any]:
    errors: list[str] = []
    completed = [row for row in rows if row.get("audit_status", "").strip()]
    for index, row in enumerate(completed, start=2):
        status = row["audit_status"].strip().casefold()
        if status not in ALLOWED_STATUSES:
            errors.append(f"row {index}: invalid audit_status={status!r}")
        if not row.get("reviewer", "").strip() or not row.get("reviewed_at", "").strip():
            errors.append(f"row {index}: reviewer and reviewed_at are required")
        if status == "incorrect" and not all(
            row.get(field, "").strip()
            for field in ("new_risk_label", "new_alignment_label", "new_severity")
        ):
            errors.append(
                f"row {index}: incorrect rows require new_risk_label, "
                "new_alignment_label, and new_severity"
            )

    if len(completed) < minimum_rows:
        errors.append(f"completed audit rows {len(completed)} < required {minimum_rows}")

    by_source: dict[str, Counter[str]] = defaultdict(Counter)
    by_action: dict[str, Counter[str]] = defaultdict(Counter)
    statuses = Counter()
    corrections = Counter()
    for row in completed:
        status = row["audit_status"].strip().casefold()
        statuses[status] += 1
        by_source[row.get("source", "unknown")][status] += 1
        by_action[row.get("action_provenance", "unknown")][status] += 1
        if status == "incorrect":
            corrections[(row.get("risk_label", ""), row.get("new_risk_label", ""))] += 1

    return {
        "schema_version": 1,
        "status": "failed" if errors else "passed",
        "errors": errors,
        "rows_in_sheet": len(rows),
        "completed_rows": len(completed),
        "status_counts": dict(sorted(statuses.items())),
        "by_source": {key: dict(sorted(value.items())) for key, value in sorted(by_source.items())},
        "by_action_provenance": {
            key: dict(sorted(value.items())) for key, value in sorted(by_action.items())
        },
        "risk_corrections": [
            {"from": old, "to": new, "count": count}
            for (old, new), count in sorted(corrections.items())
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate and summarize a user-completed audit sheet"
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--minimum-rows", type=int, default=200)
    args = parser.parse_args()
    with args.input.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    report = summarize(rows, args.minimum_rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    if report["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
