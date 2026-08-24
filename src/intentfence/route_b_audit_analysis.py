from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from intentfence.constants import RISK_LABELS, TASK_ALIGNMENT_LABELS
from intentfence.data import file_sha256
from intentfence.route_b_audit import (
    ALIGNMENT_REVIEW_FIELDS,
    RISK_REVIEW_FIELDS,
)

REVIEW_STATUSES = frozenset({"completed", "unable_to_determine"})
ACTION_REALISM_LABELS = frozenset({"realistic", "unrealistic", "ambiguous"})


def _read_csv(path: Path, expected_fields: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != expected_fields:
            raise ValueError(f"unexpected columns in {path}: {reader.fieldnames}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"review sheet is empty: {path}")
    audit_ids = [row["audit_id"] for row in rows]
    if len(audit_ids) != len(set(audit_ids)):
        raise ValueError(f"duplicate audit_id in {path}")
    return rows


def _parse_time(value: str, *, path: Path, audit_id: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid reviewed_at in {path}/{audit_id}: {value!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"reviewed_at lacks timezone in {path}/{audit_id}")


def _content_hash(row: dict[str, str], *, task: str) -> str:
    import hashlib

    payload = [
        row["sample_id"],
        row["split"],
        row["scenario"],
        row["user_goal"],
        row["untrusted_content"],
    ]
    if task == "alignment":
        payload.append(row["proposed_action"])
    return hashlib.sha256("\x1f".join(payload).encode("utf-8")).hexdigest()


def _validate_sheet(
    rows: list[dict[str, str]],
    truth: dict[str, dict[str, Any]],
    *,
    path: Path,
    task: str,
) -> tuple[str, list[str]]:
    errors: list[str] = []
    reviewers = {row["reviewer"].strip() for row in rows if row["reviewer"].strip()}
    if len(reviewers) != 1:
        errors.append(f"{path}: expected exactly one stable reviewer ID, got {sorted(reviewers)}")
    reviewer = next(iter(reviewers), "")
    if set(row["audit_id"] for row in rows) != set(truth):
        errors.append(f"{path}: audit_id set differs from sealed selection")
    for row in rows:
        audit_id = row["audit_id"]
        expected = truth.get(audit_id)
        if expected is None:
            continue
        if row["sample_id"] != expected["sample_id"]:
            errors.append(f"{path}/{audit_id}: sample_id was modified")
        if _content_hash(row, task=task) != expected["content_hash"]:
            errors.append(f"{path}/{audit_id}: immutable review content was modified")
        status = row["review_status"].strip()
        row["review_status"] = status
        if status not in REVIEW_STATUSES:
            errors.append(f"{path}/{audit_id}: invalid review_status={status!r}")
            continue
        if not row["reviewer"].strip():
            errors.append(f"{path}/{audit_id}: reviewer is missing")
        if not row["reviewed_at"].strip():
            errors.append(f"{path}/{audit_id}: reviewed_at is missing")
        else:
            try:
                _parse_time(row["reviewed_at"], path=path, audit_id=audit_id)
            except ValueError as exc:
                errors.append(str(exc))
        label_field = "risk_label_review" if task == "risk" else "task_alignment_label_review"
        allowed = set(RISK_LABELS if task == "risk" else TASK_ALIGNMENT_LABELS)
        label = row[label_field].strip()
        row[label_field] = label
        if status == "completed" and label not in allowed:
            errors.append(f"{path}/{audit_id}: invalid {label_field}={label!r}")
        if status == "unable_to_determine" and not row["notes"].strip():
            errors.append(f"{path}/{audit_id}: unable_to_determine requires notes")
        if task == "alignment" and status == "completed":
            realism = row["action_realism_review"].strip()
            row["action_realism_review"] = realism
            if realism not in ACTION_REALISM_LABELS:
                errors.append(
                    f"{path}/{audit_id}: invalid action_realism_review={realism!r}"
                )
    return reviewer, errors


def _cohen_kappa(left: list[str], right: list[str], labels: tuple[str, ...]) -> float | None:
    if len(left) != len(right) or not left:
        return None
    total = len(left)
    observed = sum(a == b for a, b in zip(left, right, strict=True)) / total
    left_counts = Counter(left)
    right_counts = Counter(right)
    expected = sum(
        (left_counts[label] / total) * (right_counts[label] / total) for label in labels
    )
    if expected == 1:
        return 1.0 if observed == 1 else None
    return (observed - expected) / (1 - expected)


def _task_metrics(
    left_rows: list[dict[str, str]],
    right_rows: list[dict[str, str]],
    truth: dict[str, dict[str, Any]],
    *,
    task: str,
) -> dict[str, Any]:
    label_field = "risk_label_review" if task == "risk" else "task_alignment_label_review"
    truth_field = "seed_risk_label" if task == "risk" else "seed_task_alignment_label"
    labels = RISK_LABELS if task == "risk" else TASK_ALIGNMENT_LABELS
    left = {row["audit_id"]: row for row in left_rows}
    right = {row["audit_id"]: row for row in right_rows}
    common_completed = [
        audit_id
        for audit_id in sorted(truth)
        if left[audit_id]["review_status"] == "completed"
        and right[audit_id]["review_status"] == "completed"
    ]
    left_labels = [left[audit_id][label_field] for audit_id in common_completed]
    right_labels = [right[audit_id][label_field] for audit_id in common_completed]
    agreement = (
        sum(a == b for a, b in zip(left_labels, right_labels, strict=True))
        / len(common_completed)
        if common_completed
        else 0.0
    )
    per_reviewer_seed: dict[str, Any] = {}
    for name, rows in (("reviewer_a", left), ("reviewer_b", right)):
        by_class: dict[str, list[bool]] = defaultdict(list)
        completed = 0
        correct = 0
        for audit_id, expected in truth.items():
            row = rows[audit_id]
            if row["review_status"] != "completed":
                continue
            completed += 1
            is_correct = row[label_field] == expected[truth_field]
            correct += int(is_correct)
            by_class[str(expected[truth_field])].append(is_correct)
        per_reviewer_seed[name] = {
            "completed": completed,
            "completed_fraction": completed / len(truth),
            "overall_agreement": correct / completed if completed else 0.0,
            "per_seed_class_agreement": {
                label: sum(values) / len(values) if values else 0.0
                for label, values in sorted(by_class.items())
            },
        }
    result: dict[str, Any] = {
        "rows": len(truth),
        "both_completed": len(common_completed),
        "raw_interreviewer_agreement": agreement,
        "cohen_kappa": _cohen_kappa(left_labels, right_labels, labels),
        "seed_agreement": per_reviewer_seed,
        "disagreement_audit_ids": [
            audit_id
            for audit_id in common_completed
            if left[audit_id][label_field] != right[audit_id][label_field]
        ],
    }
    if task == "alignment":
        realism_values = [
            row["action_realism_review"]
            for rows in (left, right)
            for row in rows.values()
            if row["review_status"] == "completed"
        ]
        result["action_realism"] = {
            "counts": dict(sorted(Counter(realism_values).items())),
            "realistic_fraction": (
                realism_values.count("realistic") / len(realism_values)
                if realism_values
                else 0.0
            ),
        }
    return result


def analyze_blind_audits(
    *,
    reviewer_a_risk: str | Path,
    reviewer_b_risk: str | Path,
    reviewer_a_alignment: str | Path,
    reviewer_b_alignment: str | Path,
    sealed_seed_labels: str | Path,
    audit_manifest: str | Path,
    policy: dict[str, Any],
) -> dict[str, Any]:
    paths = {
        "reviewer_a_risk": Path(reviewer_a_risk),
        "reviewer_b_risk": Path(reviewer_b_risk),
        "reviewer_a_alignment": Path(reviewer_a_alignment),
        "reviewer_b_alignment": Path(reviewer_b_alignment),
    }
    audit_manifest_path = Path(audit_manifest)
    audit_manifest_payload = json.loads(audit_manifest_path.read_text(encoding="utf-8"))
    claimed_manifest_hash = audit_manifest_payload.pop("sha256", None)
    import hashlib

    actual_manifest_hash = hashlib.sha256(
        json.dumps(
            audit_manifest_payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()
    if claimed_manifest_hash != actual_manifest_hash:
        return {
            "status": "invalid_review_package",
            "validation_errors": ["audit manifest self-hash mismatch"],
            "formal_training_authorized": False,
        }
    sealed_path = Path(sealed_seed_labels)
    if (
        file_sha256(sealed_path)
        != audit_manifest_payload.get("sealed_seed_labels", {}).get("sha256")
    ):
        return {
            "status": "invalid_review_package",
            "validation_errors": ["sealed seed-label hash mismatch"],
            "formal_training_authorized": False,
        }
    truth_payload = json.loads(sealed_path.read_text(encoding="utf-8"))
    truth = {
        task: {row["audit_id"]: row for row in truth_payload[task]}
        for task in ("risk", "alignment")
    }
    sheets = {
        "reviewer_a_risk": _read_csv(paths["reviewer_a_risk"], RISK_REVIEW_FIELDS),
        "reviewer_b_risk": _read_csv(paths["reviewer_b_risk"], RISK_REVIEW_FIELDS),
        "reviewer_a_alignment": _read_csv(
            paths["reviewer_a_alignment"], ALIGNMENT_REVIEW_FIELDS
        ),
        "reviewer_b_alignment": _read_csv(
            paths["reviewer_b_alignment"], ALIGNMENT_REVIEW_FIELDS
        ),
    }
    validation_errors: list[str] = []
    reviewer_ids: dict[str, str] = {}
    for name, task in (
        ("reviewer_a_risk", "risk"),
        ("reviewer_b_risk", "risk"),
        ("reviewer_a_alignment", "alignment"),
        ("reviewer_b_alignment", "alignment"),
    ):
        reviewer, errors = _validate_sheet(
            sheets[name], truth[task], path=paths[name], task=task
        )
        reviewer_ids[name] = reviewer
        validation_errors.extend(errors)
    if reviewer_ids["reviewer_a_risk"] != reviewer_ids["reviewer_a_alignment"]:
        validation_errors.append("reviewer A ID differs between Risk and Alignment sheets")
    if reviewer_ids["reviewer_b_risk"] != reviewer_ids["reviewer_b_alignment"]:
        validation_errors.append("reviewer B ID differs between Risk and Alignment sheets")
    if reviewer_ids["reviewer_a_risk"] == reviewer_ids["reviewer_b_risk"]:
        validation_errors.append("reviewer A and reviewer B must be distinct humans")
    if validation_errors:
        return {
            "status": "invalid_review_package",
            "validation_errors": validation_errors,
            "formal_training_authorized": False,
        }

    metrics = {
        "risk": _task_metrics(
            sheets["reviewer_a_risk"],
            sheets["reviewer_b_risk"],
            truth["risk"],
            task="risk",
        ),
        "alignment": _task_metrics(
            sheets["reviewer_a_alignment"],
            sheets["reviewer_b_alignment"],
            truth["alignment"],
            task="alignment",
        ),
    }
    gates = policy["audit"]["preregistered_quality_gates"]
    gate_results: dict[str, bool] = {}
    for task in ("risk", "alignment"):
        task_metrics = metrics[task]
        gate_results[f"{task}_completion"] = all(
            item["completed_fraction"] >= gates["completed_fraction_minimum"]
            for item in task_metrics["seed_agreement"].values()
        )
        gate_results[f"{task}_raw_agreement"] = (
            task_metrics["raw_interreviewer_agreement"]
            >= gates["raw_interreviewer_agreement_minimum"]
        )
        gate_results[f"{task}_kappa"] = (
            task_metrics["cohen_kappa"] is not None
            and task_metrics["cohen_kappa"] >= gates["cohen_kappa_minimum"]
        )
        gate_results[f"{task}_per_seed_class"] = all(
            value >= gates["per_seed_class_agreement_minimum"]
            for reviewer in task_metrics["seed_agreement"].values()
            for value in reviewer["per_seed_class_agreement"].values()
        )
    gate_results["action_realism"] = (
        metrics["alignment"]["action_realism"]["realistic_fraction"]
        >= gates["action_realism_realistic_fraction_minimum"]
    )
    disagreements = (
        len(metrics["risk"]["disagreement_audit_ids"])
        + len(metrics["alignment"]["disagreement_audit_ids"])
    )
    gates_passed = all(gate_results.values())
    status = (
        "quality_gates_failed_revise_corpus"
        if not gates_passed
        else "quality_gates_passed_adjudication_required"
        if disagreements
        else "quality_gates_passed"
    )
    return {
        "status": status,
        "validation_errors": [],
        "reviewer_ids": {
            "reviewer_a": reviewer_ids["reviewer_a_risk"],
            "reviewer_b": reviewer_ids["reviewer_b_risk"],
        },
        "received_files": {
            name: {"path": str(path.resolve()), "sha256": file_sha256(path)}
            for name, path in paths.items()
        },
        "audit_manifest": {
            "path": str(audit_manifest_path.resolve()),
            "sha256": file_sha256(audit_manifest_path),
            "sealed_sha256": claimed_manifest_hash,
        },
        "metrics": metrics,
        "quality_gates": gate_results,
        "quality_gates_passed": gates_passed,
        "adjudication_required": disagreements > 0,
        "formal_training_authorized": False,
    }
