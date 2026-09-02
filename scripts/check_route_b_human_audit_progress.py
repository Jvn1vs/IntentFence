"""Report Route B human-audit completion without mutating or revealing seed labels."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from intentfence.constants import RISK_LABELS, TASK_ALIGNMENT_LABELS
from intentfence.route_b_audit import (
    ALIGNMENT_REVIEW_FIELDS,
    HUMAN_REVIEWER_ATTESTATION_KIND,
    HUMAN_REVIEWER_ATTESTATION_SCHEMA_VERSION,
    RISK_REVIEW_FIELDS,
)

REVIEW_STATUSES = frozenset({"completed", "unable_to_determine"})
ACTION_REALISM_LABELS = frozenset({"realistic", "unrealistic", "ambiguous"})
DEFAULT_AUDIT_DIR = Path("data/interim/route_b_v2_candidate_8_human_audit_v2")

SHEET_SPECS: dict[str, dict[str, Any]] = {
    "reviewer_a_risk.csv": {
        "slot": "reviewer_a",
        "task": "risk",
        "fields": RISK_REVIEW_FIELDS,
        "expected_key": "risk_rows",
    },
    "reviewer_b_risk.csv": {
        "slot": "reviewer_b",
        "task": "risk",
        "fields": RISK_REVIEW_FIELDS,
        "expected_key": "risk_rows",
    },
    "reviewer_a_alignment.csv": {
        "slot": "reviewer_a",
        "task": "alignment",
        "fields": ALIGNMENT_REVIEW_FIELDS,
        "expected_key": "alignment_rows",
    },
    "reviewer_b_alignment.csv": {
        "slot": "reviewer_b",
        "task": "alignment",
        "fields": ALIGNMENT_REVIEW_FIELDS,
        "expected_key": "alignment_rows",
    },
}


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _valid_timestamp(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _nested_counter_values(values: dict[str, Counter[str]]) -> dict[str, dict[str, int]]:
    return {
        field: dict(sorted(counter.items()))
        for field, counter in sorted(values.items())
        if counter
    }


def _sheet_progress(
    path: Path,
    *,
    task: str,
    expected_fields: tuple[str, ...],
    expected_rows: int | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": str(path.resolve()),
        "expected_rows": expected_rows,
        "rows": 0,
        "complete_rows": 0,
        "missing_fields": {},
        "invalid_values": {},
        "reviewer_ids": [],
        "status": "missing",
    }
    if not path.is_file():
        return result

    missing_fields: Counter[str] = Counter()
    invalid_values: dict[str, Counter[str]] = {}
    reviewer_ids: set[str] = set()

    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            actual_fields = tuple(reader.fieldnames or ())
            schema_ok = actual_fields == expected_fields
            if not schema_ok:
                result["schema_error"] = {
                    "expected": list(expected_fields),
                    "actual": list(actual_fields),
                }
            for row in reader:
                result["rows"] += 1
                row_missing: set[str] = set()
                row_invalid = False

                status = _text(row.get("review_status"))
                if not status:
                    row_missing.add("review_status")
                elif status not in REVIEW_STATUSES:
                    invalid_values.setdefault("review_status", Counter())[status] += 1
                    row_invalid = True

                reviewer = _text(row.get("reviewer"))
                if reviewer:
                    reviewer_ids.add(reviewer)
                else:
                    row_missing.add("reviewer")

                reviewed_at = _text(row.get("reviewed_at"))
                if not reviewed_at:
                    row_missing.add("reviewed_at")
                elif not _valid_timestamp(reviewed_at):
                    invalid_values.setdefault("reviewed_at", Counter())[reviewed_at] += 1
                    row_invalid = True

                label_field = (
                    "risk_label_review"
                    if task == "risk"
                    else "task_alignment_label_review"
                )
                if status == "completed":
                    label = _text(row.get(label_field))
                    if not label:
                        row_missing.add(label_field)
                    else:
                        allowed = set(RISK_LABELS if task == "risk" else TASK_ALIGNMENT_LABELS)
                        if label not in allowed:
                            invalid_values.setdefault(label_field, Counter())[label] += 1
                            row_invalid = True
                    if task == "alignment":
                        realism = _text(row.get("action_realism_review"))
                        if not realism:
                            row_missing.add("action_realism_review")
                        elif realism not in ACTION_REALISM_LABELS:
                            invalid_values.setdefault("action_realism_review", Counter())[realism] += 1
                            row_invalid = True
                elif status == "unable_to_determine" and not _text(row.get("notes")):
                    row_missing.add("notes")

                for field in row_missing:
                    missing_fields[field] += 1
                if not row_missing and not row_invalid and schema_ok:
                    result["complete_rows"] += 1
    except (OSError, csv.Error, UnicodeError) as exc:
        result["status"] = "invalid"
        result["error"] = str(exc)
        return result

    result["missing_fields"] = dict(sorted(missing_fields.items()))
    result["invalid_values"] = _nested_counter_values(invalid_values)
    result["reviewer_ids"] = sorted(reviewer_ids)
    if "schema_error" in result:
        result["status"] = "invalid"
    elif expected_rows is not None and result["rows"] == expected_rows:
        result["status"] = (
            "complete" if result["complete_rows"] == expected_rows else "incomplete"
        )
    else:
        result["status"] = "incomplete"
    return result


def _attestation_progress(path: Path, *, reviewer_slot: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": str(path.resolve()),
        "reviewer_slot": reviewer_slot,
        "status": "missing",
        "missing_fields": [],
        "invalid_fields": {},
    }
    if not path.is_file():
        return result
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        result["status"] = "invalid"
        result["error"] = str(exc)
        return result
    if not isinstance(payload, dict):
        result["status"] = "invalid"
        result["error"] = "attestation must be a JSON object"
        return result

    missing: list[str] = []
    invalid: dict[str, str] = {}
    if payload.get("schema_version") != HUMAN_REVIEWER_ATTESTATION_SCHEMA_VERSION:
        invalid["schema_version"] = _text(payload.get("schema_version"))
    if payload.get("reviewer_slot") != reviewer_slot:
        invalid["reviewer_slot"] = _text(payload.get("reviewer_slot"))
    reviewer_id = _text(payload.get("reviewer_id"))
    if not reviewer_id:
        missing.append("reviewer_id")
    if payload.get("reviewer_kind") != HUMAN_REVIEWER_ATTESTATION_KIND:
        invalid["reviewer_kind"] = _text(payload.get("reviewer_kind"))
    if payload.get("independence_declared") is not True:
        invalid["independence_declared"] = _text(payload.get("independence_declared"))
    attested_at = _text(payload.get("attested_at"))
    if not attested_at:
        missing.append("attested_at")
    elif not _valid_timestamp(attested_at):
        invalid["attested_at"] = attested_at

    result["missing_fields"] = sorted(missing)
    result["invalid_fields"] = dict(sorted(invalid.items()))
    result["reviewer_id"] = reviewer_id
    result["status"] = "complete" if not missing and not invalid else "incomplete"
    return result


def summarize_audit_progress(audit_dir: str | Path) -> dict[str, Any]:
    """Return a read-only completion summary for the two-human audit package."""
    root = Path(audit_dir).resolve()
    report: dict[str, Any] = {
        "audit_dir": str(root),
        "status": "incomplete",
        "formal_training_authorized": False,
        "sheets": {},
        "attestations": {},
        "reviewer_identity": {},
        "blocking_reasons": [],
    }

    manifest_path = root / "audit_manifest.json"
    expected_rows: dict[str, int | None] = {"risk_rows": None, "alignment_rows": None}
    if not manifest_path.is_file():
        report["blocking_reasons"].append("audit_manifest.json is missing")
    else:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for key in expected_rows:
                value = manifest.get(key)
                if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                    expected_rows[key] = value
                else:
                    report["blocking_reasons"].append(f"manifest field {key} is invalid")
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            report["blocking_reasons"].append(f"audit manifest is invalid: {exc}")

    for filename, spec in SHEET_SPECS.items():
        sheet = _sheet_progress(
            root / filename,
            task=str(spec["task"]),
            expected_fields=spec["fields"],
            expected_rows=expected_rows[str(spec["expected_key"])],
        )
        report["sheets"][filename] = sheet
        if sheet["status"] != "complete":
            report["blocking_reasons"].append(
                f"{filename}: {sheet['complete_rows']}/{sheet['expected_rows'] or '?'} complete"
            )

    for slot in ("reviewer_a", "reviewer_b"):
        attestation = _attestation_progress(
            root / f"{slot}_attestation.json", reviewer_slot=slot
        )
        report["attestations"][slot] = attestation
        if attestation["status"] != "complete":
            report["blocking_reasons"].append(f"{slot}_attestation.json is not complete")

    identity: dict[str, list[str]] = {}
    for slot in ("reviewer_a", "reviewer_b"):
        ids = sorted(
            {
                reviewer_id
                for filename, sheet in report["sheets"].items()
                if SHEET_SPECS[filename]["slot"] == slot
                for reviewer_id in sheet["reviewer_ids"]
            }
        )
        identity[slot] = ids
        if len(ids) != 1:
            report["blocking_reasons"].append(
                f"{slot} must have exactly one stable reviewer ID"
            )
    report["reviewer_identity"] = identity
    if identity["reviewer_a"] and identity["reviewer_b"] and identity["reviewer_a"] == identity["reviewer_b"]:
        report["blocking_reasons"].append("reviewer A and reviewer B IDs must differ")

    if not report["blocking_reasons"]:
        report["status"] = "ready_for_deterministic_aggregation"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Report Route B human-audit progress without modifying audit files"
    )
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT_DIR)
    args = parser.parse_args()
    report = summarize_audit_progress(args.audit_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return int(report["status"] != "ready_for_deterministic_aggregation")


if __name__ == "__main__":
    raise SystemExit(main())
