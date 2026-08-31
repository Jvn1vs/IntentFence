from __future__ import annotations

import csv
import json
import runpy
from pathlib import Path

from intentfence.route_b_audit import ALIGNMENT_REVIEW_FIELDS


def _row(*, audit_id: str, label: str) -> dict[str, str]:
    return {
        "audit_id": audit_id,
        "sample_id": f"audit-alignment-{audit_id}",
        "split": "validation",
        "scenario": "mock scenario",
        "user_goal": "return the approved status",
        "untrusted_content": "untrusted note",
        "proposed_action": '{"tool":"workspace.return_result","arguments":{}}',
        "task_alignment_label_review": label,
        "action_realism_review": "realistic",
        "review_status": "completed",
        "reviewer": "reviewer-a" if label == "aligned" else "reviewer-b",
        "reviewed_at": "2026-08-30T00:00:00+00:00",
        "notes": "",
    }


def _write(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ALIGNMENT_REVIEW_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def test_builds_blind_project_owner_adjudication_package(tmp_path: Path) -> None:
    builder = runpy.run_path("scripts/build_route_b_ai_adjudication_package.py")[
        "build_package"
    ]
    left = tmp_path / "reviewer_a_alignment.csv"
    right = tmp_path / "reviewer_b_alignment.csv"
    _write(left, [_row(audit_id="a" * 20, label="aligned")])
    _write(right, [_row(audit_id="a" * 20, label="unrelated")])
    audit_manifest = tmp_path / "audit_manifest.json"
    ai_manifest = tmp_path / "ai_review_manifest.json"
    audit_manifest.write_text("{}", encoding="utf-8")
    ai_manifest.write_text("{}", encoding="utf-8")

    result = builder(left, right, audit_manifest, ai_manifest, tmp_path / "package")

    package = Path(result["output_dir"])
    rows = list(
        csv.DictReader((package / "alignment_adjudication.csv").open(encoding="utf-8-sig"))
    )
    manifest = json.loads((package / "adjudication_manifest.json").read_text())
    assert len(rows) == 1
    assert rows[0]["disagreement_fields"] == "task_alignment_label_review"
    assert rows[0]["final_task_alignment_label"] == ""
    assert rows[0]["adjudication_status"] == "pending_project_owner"
    assert manifest["constraints"]["sealed_seed_labels_included"] is False
    assert manifest["human_verified"] is False
    assert manifest["formal_training_authorized"] is False
