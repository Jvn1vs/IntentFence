from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from intentfence.data import file_sha256
from intentfence.route_b_audit import ALIGNMENT_REVIEW_FIELDS

IMMUTABLE_FIELDS = ALIGNMENT_REVIEW_FIELDS[:7]
DECISION_FIELDS = (
    "task_alignment_label_review",
    "action_realism_review",
    "review_status",
    "reviewer",
    "reviewed_at",
    "notes",
)
OUTPUT_FIELDS = (
    *IMMUTABLE_FIELDS,
    "reviewer_a_task_alignment_label",
    "reviewer_a_action_realism",
    "reviewer_a_status",
    "reviewer_a_id",
    "reviewer_a_reviewed_at",
    "reviewer_a_notes",
    "reviewer_b_task_alignment_label",
    "reviewer_b_action_realism",
    "reviewer_b_status",
    "reviewer_b_id",
    "reviewer_b_reviewed_at",
    "reviewer_b_notes",
    "disagreement_fields",
    "final_task_alignment_label",
    "adjudication_status",
    "adjudicator_id",
    "adjudicated_at",
    "rationale",
)


def _read_alignment(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != ALIGNMENT_REVIEW_FIELDS:
            raise ValueError(f"unexpected Alignment columns: {path}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"Alignment sheet is empty: {path}")
    if len({row["audit_id"] for row in rows}) != len(rows):
        raise ValueError(f"duplicate audit_id in {path}")
    return rows


def _disagreement_fields(left: dict[str, str], right: dict[str, str]) -> list[str]:
    fields = []
    for name in (
        "task_alignment_label_review",
        "action_realism_review",
        "review_status",
    ):
        if left[name] != right[name]:
            fields.append(name)
    return fields


def build_package(
    reviewer_a_alignment: str | Path,
    reviewer_b_alignment: str | Path,
    audit_manifest: str | Path,
    ai_review_manifest: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    reviewer_a_path = Path(reviewer_a_alignment)
    reviewer_b_path = Path(reviewer_b_alignment)
    audit_manifest_path = Path(audit_manifest)
    ai_review_manifest_path = Path(ai_review_manifest)
    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite adjudication package: {destination}")
    if not audit_manifest_path.is_file() or not ai_review_manifest_path.is_file():
        raise FileNotFoundError("audit and AI review manifests must both exist")

    left_rows = _read_alignment(reviewer_a_path)
    right_rows = _read_alignment(reviewer_b_path)
    left = {row["audit_id"]: row for row in left_rows}
    right = {row["audit_id"]: row for row in right_rows}
    if set(left) != set(right):
        raise ValueError("reviewer Alignment sheets have different audit_id sets")

    output_rows: list[dict[str, str]] = []
    for audit_id in sorted(left):
        first, second = left[audit_id], right[audit_id]
        if any(first[field] != second[field] for field in IMMUTABLE_FIELDS):
            raise ValueError(f"immutable Alignment content differs for audit_id={audit_id}")
        disagreements = _disagreement_fields(first, second)
        if not disagreements:
            continue
        output_rows.append(
            {
                **{field: first[field] for field in IMMUTABLE_FIELDS},
                "reviewer_a_task_alignment_label": first["task_alignment_label_review"],
                "reviewer_a_action_realism": first["action_realism_review"],
                "reviewer_a_status": first["review_status"],
                "reviewer_a_id": first["reviewer"],
                "reviewer_a_reviewed_at": first["reviewed_at"],
                "reviewer_a_notes": first["notes"],
                "reviewer_b_task_alignment_label": second["task_alignment_label_review"],
                "reviewer_b_action_realism": second["action_realism_review"],
                "reviewer_b_status": second["review_status"],
                "reviewer_b_id": second["reviewer"],
                "reviewer_b_reviewed_at": second["reviewed_at"],
                "reviewer_b_notes": second["notes"],
                "disagreement_fields": ";".join(disagreements),
                "final_task_alignment_label": "",
                "adjudication_status": "pending_project_owner",
                "adjudicator_id": "",
                "adjudicated_at": "",
                "rationale": "",
            }
        )
    if not output_rows:
        raise ValueError("no reviewer disagreements found; no adjudication package created")

    destination.mkdir(parents=True)
    csv_path = destination / "alignment_adjudication.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS, extrasaction="raise")
        writer.writeheader()
        writer.writerows(output_rows)
    manifest = {
        "schema_version": 1,
        "status": "awaiting_project_owner_independent_adjudication",
        "review_mode": "dual_ai_engineering_with_human_adjudication_pending",
        "formal_training_authorized": False,
        "human_verified": False,
        "constraints": {
            "source_reviews_preserved": True,
            "sealed_seed_labels_included": False,
            "adjudication_must_be_project_owner_independent": True,
            "codex_must_not_fill_final_labels": True,
        },
        "source_evidence": {
            "audit_manifest": {
                "path": str(audit_manifest_path.resolve()),
                "sha256": file_sha256(audit_manifest_path),
            },
            "ai_review_manifest": {
                "path": str(ai_review_manifest_path.resolve()),
                "sha256": file_sha256(ai_review_manifest_path),
            },
            "reviewer_a_alignment": {
                "path": str(reviewer_a_path.resolve()),
                "sha256": file_sha256(reviewer_a_path),
            },
            "reviewer_b_alignment": {
                "path": str(reviewer_b_path.resolve()),
                "sha256": file_sha256(reviewer_b_path),
            },
        },
        "adjudication_sheet": {
            "path": csv_path.name,
            "rows": len(output_rows),
            "sha256": file_sha256(csv_path),
        },
    }
    canonical = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    manifest["sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    (destination / "adjudication_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (destination / "README.md").write_text(
        "\n".join(
            (
                "# Route B project-owner adjudication package",
                "",
                "This package contains only already-submitted reviewer disagreements.",
                "It does not contain sealed seed labels and must not be used to revise source CSVs.",
                "",
                "The project owner must independently fill final_task_alignment_label,",
                "adjudicator_id, adjudicated_at, and rationale for every row, then preserve",
                "this package and the original AI reviews. Completing this package does not",
                "set human_verified or formal_training_authorized.",
                "",
            )
        ),
        encoding="utf-8",
    )
    return {"output_dir": str(destination.resolve()), "manifest": manifest}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a non-overwriting project-owner Route B AI disagreement package"
    )
    parser.add_argument("--reviewer-a-alignment", type=Path, required=True)
    parser.add_argument("--reviewer-b-alignment", type=Path, required=True)
    parser.add_argument("--audit-manifest", type=Path, required=True)
    parser.add_argument("--ai-review-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            build_package(
                args.reviewer_a_alignment,
                args.reviewer_b_alignment,
                args.audit_manifest,
                args.ai_review_manifest,
                args.output_dir,
            ),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
