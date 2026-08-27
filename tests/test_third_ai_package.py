from __future__ import annotations

import csv
import json
import runpy
from pathlib import Path


def _source_row(index: int) -> dict[str, str]:
    return {
        "audit_id": f"audit-{index}",
        "sample_id": f"sample-{index}",
        "split": "train",
        "scenario": "mock file workspace",
        "user_goal": "summarize the report",
        "untrusted_content": f"fixture content {index}",
        "proposed_action": "return_summary()",
        "task_alignment_label_review": "malicious",
        "action_realism_review": "realistic",
        "review_status": "completed",
        "reviewer": "old-reviewer",
        "reviewed_at": "2026-08-27T00:00:00+00:00",
        "notes": "old output; must not be copied",
    }


def test_third_ai_package_is_blinded_and_reproducibly_bound(tmp_path: Path) -> None:
    builder = runpy.run_path("scripts/build_route_b_third_ai_package.py")
    source_dir = tmp_path / "source"
    output_dir = tmp_path / "third"
    source_dir.mkdir()
    (source_dir / "audit_manifest.json").write_text("{}\n", encoding="utf-8")
    source_sheet = source_dir / "reviewer_a_alignment.csv"
    fields = tuple(_source_row(0))
    with source_sheet.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(_source_row(index) for index in range(400))

    result = builder["build_package"](source_dir, output_dir, seed=342)
    rows = list(
        csv.DictReader(
            (output_dir / "reviewer_c_alignment.csv").open(
                encoding="utf-8-sig", newline=""
            )
        )
    )
    manifest = json.loads(
        (output_dir / "third_ai_package_manifest.json").read_text(encoding="utf-8")
    )

    assert len(rows) == 400
    assert all(row["task_alignment_label_review"] == "" for row in rows)
    assert all(row["action_realism_review"] == "" for row in rows)
    assert not (output_dir / "sealed_seed_labels.json").exists()
    assert not (output_dir / "reviewer_a_alignment.csv").exists()
    assert manifest["constraints"]["review_all_rows_not_only_prior_disagreements"] is True
    assert result["manifest"]["submission"]["sheet"]["labels_exposed"] is False
