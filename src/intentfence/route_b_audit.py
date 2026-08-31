from __future__ import annotations

import csv
import hashlib
import json
import random
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from intentfence.data import file_sha256
from intentfence.schema import IntentSample, read_jsonl

RISK_REVIEW_FIELDS = (
    "audit_id",
    "sample_id",
    "split",
    "scenario",
    "user_goal",
    "untrusted_content",
    "risk_label_review",
    "review_status",
    "reviewer",
    "reviewed_at",
    "notes",
)
ALIGNMENT_REVIEW_FIELDS = (
    "audit_id",
    "sample_id",
    "split",
    "scenario",
    "user_goal",
    "untrusted_content",
    "proposed_action",
    "task_alignment_label_review",
    "action_realism_review",
    "review_status",
    "reviewer",
    "reviewed_at",
    "notes",
)

HUMAN_REVIEWER_ATTESTATION_SCHEMA_VERSION = 1
HUMAN_REVIEWER_ATTESTATION_KIND = "independent_human"


def _audit_id(row: IntentSample, *, task: str) -> str:
    return hashlib.sha256(f"{task}:{row.sample_id}".encode()).hexdigest()[:20]


def _blind_sample_id(*, task: str, audit_id: str) -> str:
    """Return the stable reviewer-facing identifier without exposing source labels."""
    return f"audit-{task}-{audit_id}"


def _row_hash(
    row: IntentSample,
    *,
    reviewer_sample_id: str,
    include_action: bool,
) -> str:
    payload = [
        reviewer_sample_id,
        str(row.split),
        row.scenario,
        row.user_goal,
        row.untrusted_content,
    ]
    if include_action:
        payload.append(row.proposed_action)
    return hashlib.sha256("\x1f".join(payload).encode("utf-8")).hexdigest()


def _stratified_sample(
    groups: dict[tuple[str, ...], list[IntentSample]],
    total: int,
    *,
    seed: int,
) -> list[IntentSample]:
    if total < len(groups):
        raise ValueError("sample total must be at least the number of strata")
    base, remainder = divmod(total, len(groups))
    selected: list[IntentSample] = []
    for index, (key, values) in enumerate(sorted(groups.items())):
        count = base + int(index < remainder)
        if len(values) < count:
            raise ValueError(f"stratum {key} has {len(values)} rows; requires {count}")
        generator = random.Random(f"{seed}:{'|'.join(key)}")
        selected.extend(generator.sample(sorted(values, key=lambda row: row.sample_id), count))
    return selected


def select_blind_audit_rows(
    samples: Iterable[IntentSample],
    *,
    risk_rows: int = 400,
    alignment_rows: int = 400,
    seed: int = 42,
) -> tuple[list[IntentSample], list[IntentSample]]:
    rows = list(samples)
    risk_unique: dict[str, IntentSample] = {}
    for row in rows:
        pair_group = str(row.action_pair_group)
        risk_unique.setdefault(pair_group, row)
    risk_groups: dict[tuple[str, ...], list[IntentSample]] = defaultdict(list)
    for row in risk_unique.values():
        risk_groups[(str(row.split), row.risk_label)].append(row)
    alignment_groups: dict[tuple[str, ...], list[IntentSample]] = defaultdict(list)
    for row in rows:
        alignment_groups[
            (str(row.split), row.risk_label, str(row.task_alignment_label))
        ].append(row)
    return (
        _stratified_sample(risk_groups, risk_rows, seed=seed),
        _stratified_sample(alignment_groups, alignment_rows, seed=seed + 1),
    )


def _review_rows(
    selected: list[IntentSample],
    *,
    task: str,
    reviewer_slot: str,
    seed: int,
) -> list[dict[str, str]]:
    ordered = list(selected)
    random.Random(f"{seed}:{task}:{reviewer_slot}").shuffle(ordered)
    output: list[dict[str, str]] = []
    for row in ordered:
        audit_id = _audit_id(row, task=task)
        base = {
            "audit_id": audit_id,
            "sample_id": _blind_sample_id(task=task, audit_id=audit_id),
            "split": str(row.split),
            "scenario": row.scenario,
            "user_goal": row.user_goal,
            "untrusted_content": row.untrusted_content,
            "review_status": "",
            "reviewer": "",
            "reviewed_at": "",
            "notes": "",
        }
        if task == "risk":
            base["risk_label_review"] = ""
        else:
            base["proposed_action"] = row.proposed_action
            base["task_alignment_label_review"] = ""
            base["action_realism_review"] = ""
        output.append(base)
    return output


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def _write_human_reviewer_attestation_template(path: Path, *, reviewer_slot: str) -> None:
    """Write a reviewer-supplied provenance declaration outside mutable CSV rows."""
    payload = {
        "schema_version": HUMAN_REVIEWER_ATTESTATION_SCHEMA_VERSION,
        "reviewer_slot": reviewer_slot,
        "reviewer_id": "",
        "reviewer_kind": HUMAN_REVIEWER_ATTESTATION_KIND,
        "independence_declared": False,
        "attested_at": "",
        "notes": "",
    }
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_blind_audit_package(
    input_paths: Iterable[str | Path],
    output_dir: str | Path,
    *,
    risk_rows: int = 400,
    alignment_rows: int = 400,
    seed: int = 42,
    review_mode: str = "independent_human_blind",
) -> dict[str, Any]:
    paths = [Path(path) for path in input_paths]
    destination = Path(output_dir)
    if review_mode not in {"independent_human_blind", "dual_ai_engineering"}:
        raise ValueError(f"unsupported review_mode: {review_mode}")
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite Route B audit package: {destination}")
    destination.mkdir(parents=True)
    samples = [row for path in paths for row in read_jsonl(path)]
    selected_risk, selected_alignment = select_blind_audit_rows(
        samples,
        risk_rows=risk_rows,
        alignment_rows=alignment_rows,
        seed=seed,
    )
    sheet_evidence: dict[str, Any] = {}
    for reviewer_slot, order_seed in (("reviewer_a", seed + 100), ("reviewer_b", seed + 200)):
        for task, selected, fields in (
            ("risk", selected_risk, RISK_REVIEW_FIELDS),
            ("alignment", selected_alignment, ALIGNMENT_REVIEW_FIELDS),
        ):
            path = destination / f"{reviewer_slot}_{task}.csv"
            rows = _review_rows(
                selected,
                task=task,
                reviewer_slot=reviewer_slot,
                seed=order_seed,
            )
            _write_csv(path, fields, rows)
            sheet_evidence[path.name] = {
                "rows": len(rows),
                "sha256": file_sha256(path),
                "labels_exposed": False,
            }
    reviewer_attestations: dict[str, Any] = {}
    if review_mode == "independent_human_blind":
        for reviewer_slot in ("reviewer_a", "reviewer_b"):
            attestation_path = destination / f"{reviewer_slot}_attestation.json"
            _write_human_reviewer_attestation_template(
                attestation_path, reviewer_slot=reviewer_slot
            )
            reviewer_attestations[reviewer_slot] = {
                "path": attestation_path.name,
                "required_reviewer_kind": HUMAN_REVIEWER_ATTESTATION_KIND,
                "must_declare_independence": True,
            }
    truth = {
        "risk": [
            {
                "audit_id": _audit_id(row, task="risk"),
                "sample_id": row.sample_id,
                "review_sample_id": _blind_sample_id(
                    task="risk", audit_id=_audit_id(row, task="risk")
                ),
                "content_hash": _row_hash(
                    row,
                    reviewer_sample_id=_blind_sample_id(
                        task="risk", audit_id=_audit_id(row, task="risk")
                    ),
                    include_action=False,
                ),
                "seed_risk_label": row.risk_label,
            }
            for row in sorted(selected_risk, key=lambda item: item.sample_id)
        ],
        "alignment": [
            {
                "audit_id": _audit_id(row, task="alignment"),
                "sample_id": row.sample_id,
                "review_sample_id": _blind_sample_id(
                    task="alignment", audit_id=_audit_id(row, task="alignment")
                ),
                "content_hash": _row_hash(
                    row,
                    reviewer_sample_id=_blind_sample_id(
                        task="alignment", audit_id=_audit_id(row, task="alignment")
                    ),
                    include_action=True,
                ),
                "seed_task_alignment_label": row.task_alignment_label,
            }
            for row in sorted(selected_alignment, key=lambda item: item.sample_id)
        ],
    }
    truth_path = destination / "sealed_seed_labels.json"
    truth_path.write_text(
        json.dumps(truth, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest_payload = {
        "schema_version": 1,
        "status": "awaiting_two_independent_reviewers_not_training_authorized",
        "seed": seed,
        "risk_rows": len(selected_risk),
        "alignment_rows": len(selected_alignment),
        "reviewer_slots": ["reviewer_a", "reviewer_b"],
        "review_mode": review_mode,
        "inputs": [
            {"path": str(path.resolve()), "rows": len(read_jsonl(path)), "sha256": file_sha256(path)}
            for path in paths
        ],
        "sheets": sheet_evidence,
        "sealed_seed_labels": {
            "path": truth_path.name,
            "sha256": file_sha256(truth_path),
            "must_not_be_shared_with_reviewers_before_submission": True,
        },
        "risk_strata": dict(
            sorted(Counter(f"{row.split}|{row.risk_label}" for row in selected_risk).items())
        ),
        "alignment_strata": dict(
            sorted(
                Counter(
                    f"{row.split}|{row.risk_label}|{row.task_alignment_label}"
                    for row in selected_alignment
                ).items()
            )
        ),
        "formal_training_authorized": False,
    }
    if reviewer_attestations:
        manifest_payload["reviewer_attestations"] = reviewer_attestations
    serialized = json.dumps(
        manifest_payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    manifest_payload["sha256"] = hashlib.sha256(serialized.encode()).hexdigest()
    manifest_path = destination / "audit_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest_payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"manifest": manifest_payload, "manifest_path": str(manifest_path)}
