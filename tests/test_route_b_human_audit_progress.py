from __future__ import annotations

import csv
import json
from pathlib import Path

from intentfence.route_b_audit import ALIGNMENT_REVIEW_FIELDS, RISK_REVIEW_FIELDS
from scripts.check_route_b_human_audit_progress import summarize_audit_progress


def _write_sheet(path: Path, fields: tuple[str, ...], *, slot: str, task: str, complete: bool) -> None:
    rows = []
    for index in range(2):
        row = {field: f"fixture-{task}-{index}" for field in fields}
        row.update(
            {
                "audit_id": f"{task}-{index}",
                "sample_id": f"sample-{task}-{index}",
                "reviewer": slot,
            }
        )
        if complete:
            row.update(
                {
                    "review_status": "completed",
                    "reviewer": slot,
                    "reviewed_at": "2026-09-02T12:00:00+08:00",
                }
            )
            if task == "risk":
                row["risk_label_review"] = "benign"
            else:
                row["task_alignment_label_review"] = "aligned"
                row["action_realism_review"] = "realistic"
        else:
            for field in fields:
                if field in {
                    "risk_label_review",
                    "task_alignment_label_review",
                    "action_realism_review",
                    "review_status",
                    "reviewer",
                    "reviewed_at",
                    "notes",
                }:
                    row[field] = ""
        rows.append(row)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _write_package(root: Path, *, complete: bool) -> None:
    (root / "audit_manifest.json").write_text(
        json.dumps({"risk_rows": 2, "alignment_rows": 2}) + "\n",
        encoding="utf-8",
    )
    for slot in ("reviewer_a", "reviewer_b"):
        _write_sheet(
            root / f"{slot}_risk.csv",
            RISK_REVIEW_FIELDS,
            slot=slot,
            task="risk",
            complete=complete,
        )
        _write_sheet(
            root / f"{slot}_alignment.csv",
            ALIGNMENT_REVIEW_FIELDS,
            slot=slot,
            task="alignment",
            complete=complete,
        )
        attestation = {
            "schema_version": 1,
            "reviewer_slot": slot,
            "reviewer_id": slot,
            "reviewer_kind": "independent_human",
            "independence_declared": complete,
            "attested_at": "2026-09-02T12:00:00+08:00" if complete else "",
        }
        (root / f"{slot}_attestation.json").write_text(
            json.dumps(attestation) + "\n", encoding="utf-8"
        )


def test_progress_report_is_read_only_and_distinguishes_incomplete_from_ready(
    tmp_path: Path,
) -> None:
    _write_package(tmp_path, complete=False)
    incomplete = summarize_audit_progress(tmp_path)

    assert incomplete["status"] == "incomplete"
    assert incomplete["formal_training_authorized"] is False
    assert incomplete["sheets"]["reviewer_a_risk.csv"]["complete_rows"] == 0
    assert "review_status" in incomplete["sheets"]["reviewer_a_risk.csv"]["missing_fields"]

    _write_package(tmp_path, complete=True)
    ready = summarize_audit_progress(tmp_path)

    assert ready["status"] == "ready_for_deterministic_aggregation"
    assert ready["sheets"]["reviewer_a_alignment.csv"]["complete_rows"] == 2
    assert ready["attestations"]["reviewer_a"]["status"] == "complete"


def test_candidate_8_analysis_wrapper_is_gated_and_fixed_to_the_audit_package() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    script = (
        repository_root / "scripts" / "run_route_b_candidate_8_audit_analysis.ps1"
    ).read_text(encoding="utf-8")

    assert "check_route_b_human_audit_progress.py" in script
    assert "if ($progressExitCode -ne 0)" in script
    assert "analyze_route_b_blind_audits.py" in script
    assert '"sealed_seed_labels.json"' in script
    assert '"audit_analysis.json"' in script
    assert "Refusing to overwrite existing audit analysis" in script
