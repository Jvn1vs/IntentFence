from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from collections import Counter, defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from intentfence.constants import RISK_LABELS
from intentfence.data import file_sha256
from intentfence.schema import IntentSample, read_jsonl

ALLOWED_STATUSES = {"correct", "incorrect", "ambiguous"}
AUDIT_SELECTION_ALGORITHM = "deterministic_stratified_round_robin"
AUDIT_SELECTION_ALGORITHM_VERSION = 1
AUDIT_SELECTION_SEED = 42
AUDIT_REQUIRED_GROUPING = ("source", "risk_label", "action_provenance")
IMMUTABLE_AUDIT_FIELDS = (
    "sample_id",
    "source",
    "scenario",
    "adapter_profile",
    "action_provenance",
    "risk_label",
    "alignment_label",
    "severity",
    "user_goal",
    "untrusted_content",
    "proposed_action",
)
EDITABLE_AUDIT_FIELDS = (
    "audit_status",
    "new_risk_label",
    "new_alignment_label",
    "new_severity",
    "notes",
    "reviewer",
    "reviewed_at",
)


def deterministic_stratified_selection(
    samples: list[IntentSample],
    *,
    requested_size: int,
    seed: int,
    grouping: tuple[str, ...] | list[str],
) -> list[IntentSample]:
    """Select a reproducible round-robin sample from sorted strata."""

    if type(requested_size) is not int or requested_size <= 0:
        raise ValueError("audit requested_size must be a positive integer")
    if type(seed) is not int:
        raise ValueError("audit seed must be an integer")
    if not grouping or not all(isinstance(field, str) and field for field in grouping):
        raise ValueError("audit grouping fields are missing or invalid")

    strata: dict[tuple[str, ...], list[IntentSample]] = defaultdict(list)
    for sample in samples:
        try:
            key = tuple(str(getattr(sample, field)) for field in grouping)
        except AttributeError as exc:
            raise ValueError(f"unknown audit grouping field: {exc.name}") from exc
        strata[key].append(sample)

    rng = random.Random(seed)
    for key in sorted(strata):
        strata[key].sort(key=lambda sample: sample.sample_id)
        rng.shuffle(strata[key])
    selected: list[IntentSample] = []
    target_size = min(requested_size, len(samples))
    keys = sorted(strata)
    while len(selected) < target_size:
        for key in keys:
            if strata[key] and len(selected) < target_size:
                selected.append(strata[key].pop())
    rng.shuffle(selected)
    return selected


def audit_row_digest(row: Mapping[str, Any]) -> str:
    """Hash the review-visible fields that must not change after sheet creation."""

    payload = {
        field: "" if row.get(field) is None else str(row.get(field))
        for field in IMMUTABLE_AUDIT_FIELDS
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_audit_key(
    key_path: Path,
    audit_path: Path,
    rows: list[dict[str, str]],
    *,
    expected_input: Path | None = None,
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    try:
        key = json.loads(key_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [f"cannot read audit key {key_path}: {exc}"]
    if not isinstance(key, dict):
        return {}, [f"audit key must contain an object: {key_path}"]
    if key.get("schema_version") != 2:
        errors.append("audit key schema_version must be 2")
    if key.get("selection_algorithm") != AUDIT_SELECTION_ALGORITHM:
        errors.append("audit key selection_algorithm does not match the frozen contract")
    if key.get("selection_algorithm_version") != AUDIT_SELECTION_ALGORITHM_VERSION:
        errors.append("audit key selection_algorithm_version does not match the frozen contract")
    seed = key.get("seed")
    if type(seed) is not int or seed != AUDIT_SELECTION_SEED:
        errors.append("audit key seed does not match the frozen contract")
    requested_size = key.get("requested_size")
    if type(requested_size) is not int or requested_size <= 0:
        errors.append("audit key requested_size is missing or invalid")
    grouping = key.get("required_grouping")
    if grouping != list(AUDIT_REQUIRED_GROUPING):
        errors.append("audit key required_grouping does not match the frozen contract")
    raw_ids = key.get("sample_ids")
    if not isinstance(raw_ids, list) or not all(isinstance(value, str) for value in raw_ids):
        errors.append("audit key sample_ids are missing or invalid")
        key_ids: list[str] = []
    else:
        key_ids = raw_ids
    sheet_ids = [row.get("sample_id", "").strip() for row in rows]
    if any(not sample_id for sample_id in sheet_ids):
        errors.append("audit sheet contains an empty sample_id")
    if len(sheet_ids) != len(set(sheet_ids)):
        errors.append("audit sheet contains duplicate sample_id values")
    if sheet_ids != key_ids:
        errors.append("audit sheet sample ID order does not match the sealed audit key")
    if key.get("selected") != len(key_ids):
        errors.append("audit key selected count does not match sample_ids")
    raw_sheet = key.get("audit_sheet")
    if not isinstance(raw_sheet, str) or Path(raw_sheet).resolve() != audit_path.resolve():
        errors.append("audit sheet path does not match the sealed audit key")

    expected_columns = set((*IMMUTABLE_AUDIT_FIELDS, *EDITABLE_AUDIT_FIELDS))
    if any(set(row) != expected_columns for row in rows):
        errors.append("audit sheet columns do not match the immutable review schema")

    raw_digests = key.get("immutable_row_sha256")
    if not isinstance(raw_digests, dict) or not all(
        isinstance(sample_id, str) and isinstance(digest, str)
        for sample_id, digest in raw_digests.items()
    ):
        errors.append("audit key immutable row digests are missing or invalid")
        key_digests: dict[str, str] = {}
    else:
        key_digests = raw_digests
        if set(key_digests) != set(key_ids):
            errors.append("audit key immutable row digests do not match sample_ids")
    if key.get("immutable_fields") != list(IMMUTABLE_AUDIT_FIELDS):
        errors.append("audit key immutable field contract is missing or invalid")

    raw_input = key.get("input")
    canonical_rows = []
    if not isinstance(raw_input, str):
        errors.append("audit key canonical input path is missing or invalid")
    else:
        canonical_path = Path(raw_input).resolve()
        if expected_input is not None and canonical_path != expected_input.resolve():
            errors.append("audit key canonical input path does not match --input")
        expected_hash = key.get("input_sha256")
        if not canonical_path.is_file():
            errors.append(f"audit key canonical input is missing: {canonical_path}")
        elif not isinstance(expected_hash, str) or file_sha256(canonical_path) != expected_hash:
            errors.append("audit key canonical input hash does not match the current file")
        else:
            try:
                canonical_rows = read_jsonl(canonical_path)
            except (OSError, ValueError) as exc:
                errors.append(f"cannot read audit key canonical input {canonical_path}: {exc}")

    canonical_by_id = {sample.sample_id: sample for sample in canonical_rows}
    if (
        canonical_rows
        and type(requested_size) is int
        and requested_size > 0
        and type(seed) is int
        and seed == AUDIT_SELECTION_SEED
        and grouping == list(AUDIT_REQUIRED_GROUPING)
        and key.get("selection_algorithm") == AUDIT_SELECTION_ALGORITHM
        and key.get("selection_algorithm_version") == AUDIT_SELECTION_ALGORITHM_VERSION
    ):
        replayed_ids = [
            sample.sample_id
            for sample in deterministic_stratified_selection(
                canonical_rows,
                requested_size=requested_size,
                seed=seed,
                grouping=AUDIT_REQUIRED_GROUPING,
            )
        ]
        if key_ids != replayed_ids:
            errors.append("audit key sample_ids do not match deterministic selection replay")
    sheet_by_id = {
        row.get("sample_id", "").strip(): row
        for row in rows
        if row.get("sample_id", "").strip()
    }
    for sample_id in key_ids:
        canonical = canonical_by_id.get(sample_id)
        sheet_row = sheet_by_id.get(sample_id)
        stored_digest = key_digests.get(sample_id)
        if canonical is None:
            errors.append(f"audit key sample is absent from canonical input: {sample_id}")
            continue
        canonical_digest = audit_row_digest(canonical.model_dump(mode="json"))
        if stored_digest != canonical_digest:
            errors.append(f"audit key immutable digest does not match canonical input: {sample_id}")
        if sheet_row is not None and audit_row_digest(sheet_row) != canonical_digest:
            errors.append(f"audit sheet immutable fields changed: {sample_id}")
    return key, errors


def summarize(rows: list[dict[str, str]], minimum_rows: int) -> dict[str, Any]:
    errors: list[str] = []
    completed = [row for row in rows if row.get("audit_status", "").strip()]
    for index, row in enumerate(completed, start=2):
        status = row["audit_status"].strip().casefold()
        if status not in ALLOWED_STATUSES:
            errors.append(f"row {index}: invalid audit_status={status!r}")
        if not row.get("reviewer", "").strip() or not row.get("reviewed_at", "").strip():
            errors.append(f"row {index}: reviewer and reviewed_at are required")
        if status in {"incorrect", "ambiguous"} and not row.get("notes", "").strip():
            errors.append(f"row {index}: incorrect and ambiguous decisions require notes")
        if status == "incorrect":
            required = ("new_risk_label", "new_alignment_label", "new_severity")
            if not all(row.get(field, "").strip() for field in required):
                errors.append(
                    f"row {index}: incorrect rows require new_risk_label, "
                    "new_alignment_label, and new_severity"
                )
                continue
            risk_label = row["new_risk_label"].strip()
            alignment_raw = row["new_alignment_label"].strip()
            severity_raw = row["new_severity"].strip()
            if risk_label not in RISK_LABELS:
                errors.append(
                    f"row {index}: new_risk_label must be one of {RISK_LABELS}"
                )
            try:
                alignment = int(alignment_raw)
            except ValueError:
                alignment = -1
            if alignment not in {0, 1} or alignment_raw not in {"0", "1"}:
                errors.append(f"row {index}: new_alignment_label must be 0 or 1")
            try:
                severity = int(severity_raw)
            except ValueError:
                severity = -1
            if severity not in range(5) or severity_raw not in {"0", "1", "2", "3", "4"}:
                errors.append(f"row {index}: new_severity must be an integer from 0 to 4")
            if risk_label == "benign":
                if alignment != 0:
                    errors.append(
                        f"row {index}: benign correction requires new_alignment_label=0"
                    )
                if severity > 1:
                    errors.append(f"row {index}: benign correction requires new_severity<=1")
            elif risk_label in RISK_LABELS and alignment != 1:
                errors.append(
                    f"row {index}: non-benign correction requires new_alignment_label=1"
                )

    if len(completed) < minimum_rows:
        errors.append(f"completed audit rows {len(completed)} < required {minimum_rows}")

    by_source: dict[str, Counter[str]] = defaultdict(Counter)
    by_action: dict[str, Counter[str]] = defaultdict(Counter)
    by_scenario: dict[str, Counter[str]] = defaultdict(Counter)
    statuses = Counter()
    corrections = Counter()
    reviewers = Counter()
    for row in completed:
        status = row["audit_status"].strip().casefold()
        statuses[status] += 1
        by_source[row.get("source", "unknown")][status] += 1
        by_action[row.get("action_provenance", "unknown")][status] += 1
        by_scenario[row.get("scenario", "unknown")][status] += 1
        reviewers[row.get("reviewer", "unknown").strip() or "unknown"] += 1
        if status == "incorrect":
            corrections[(row.get("risk_label", ""), row.get("new_risk_label", ""))] += 1

    return {
        "schema_version": 1,
        "status": "failed" if errors else "passed",
        "errors": errors,
        "rows_in_sheet": len(rows),
        "completed_rows": len(completed),
        "status_counts": dict(sorted(statuses.items())),
        "status_rates": {
            status: count / len(completed) for status, count in sorted(statuses.items())
        }
        if completed
        else {},
        "reviewer_counts": dict(sorted(reviewers.items())),
        "by_source": {key: dict(sorted(value.items())) for key, value in sorted(by_source.items())},
        "by_action_provenance": {
            key: dict(sorted(value.items())) for key, value in sorted(by_action.items())
        },
        "by_scenario": {
            key: dict(sorted(value.items())) for key, value in sorted(by_scenario.items())
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
    parser.add_argument("--audit-key", type=Path)
    parser.add_argument("--minimum-rows", type=int, default=200)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite audit summary: {args.output}")
    with args.input.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    key_path = args.audit_key or args.input.with_suffix(".audit_key.json")
    key, key_errors = validate_audit_key(key_path, args.input, rows)
    report = summarize(rows, args.minimum_rows)
    report["errors"] = [*key_errors, *report["errors"]]
    report["status"] = "failed" if report["errors"] else "passed"
    report["audit_sheet"] = str(args.input)
    report["audit_sheet_sha256"] = file_sha256(args.input)
    report["audit_key"] = str(key_path)
    report["audit_key_sha256"] = file_sha256(key_path) if key_path.is_file() else None
    report["audited_input"] = key.get("input")
    report["audited_input_sha256"] = key.get("input_sha256")
    if report["errors"]:
        print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
        raise SystemExit(1)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
