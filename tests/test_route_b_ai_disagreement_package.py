from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from intentfence.data import file_sha256
from scripts.build_route_b_ai_disagreement_package import (
    ALIGNMENT_FIELDS,
    ALIGNMENT_OUTPUT_FIELDS,
    RISK_FIELDS,
    RISK_OUTPUT_FIELDS,
    build_package,
    validate_package,
)


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _risk_row(audit_id: str, label: str, reviewer: str) -> dict[str, str]:
    return {
        "audit_id": audit_id,
        "sample_id": f"audit-risk-{audit_id}",
        "split": "train",
        "scenario": "synthetic",
        "user_goal": "Review a synthetic record",
        "untrusted_content": "Synthetic content",
        "risk_label_review": label,
        "review_status": "completed",
        "reviewer": reviewer,
        "reviewed_at": "2026-08-31T12:00:00+08:00",
        "notes": "",
    }


def _alignment_row(
    audit_id: str,
    label: str,
    realism: str,
    reviewer: str,
) -> dict[str, str]:
    return {
        "audit_id": audit_id,
        "sample_id": f"audit-alignment-{audit_id}",
        "split": "train",
        "scenario": "synthetic",
        "user_goal": "Review a synthetic record",
        "untrusted_content": "Synthetic content",
        "proposed_action": "read_only()",
        "task_alignment_label_review": label,
        "action_realism_review": realism,
        "review_status": "completed",
        "reviewer": reviewer,
        "reviewed_at": "2026-08-31T12:00:00+08:00",
        "notes": "",
    }


def _prepare_sources(
    tmp_path: Path,
    *,
    risk_disagreement: bool = True,
    alignment_disagreement: bool = True,
) -> dict[str, Path]:
    paths = {
        "a_risk": tmp_path / "reviewer_a_risk.csv",
        "b_risk": tmp_path / "reviewer_b_risk.csv",
        "a_alignment": tmp_path / "reviewer_a_alignment.csv",
        "b_alignment": tmp_path / "reviewer_b_alignment.csv",
        "audit_manifest": tmp_path / "audit_manifest.json",
        "ai_manifest": tmp_path / "ai_review_manifest.json",
        "analysis": tmp_path / "ai_review_analysis.json",
    }
    a_id, b_id = "codex_ai_a", "codex_ai_b"
    _write_csv(
        paths["a_risk"],
        RISK_FIELDS,
        [_risk_row("risk-1", "instruction_hijacking", a_id), _risk_row("risk-2", "benign", a_id)],
    )
    _write_csv(
        paths["b_risk"],
        RISK_FIELDS,
        [
            _risk_row("risk-1", "tool_manipulation" if risk_disagreement else "instruction_hijacking", b_id),
            _risk_row("risk-2", "benign", b_id),
        ],
    )
    _write_csv(
        paths["a_alignment"],
        ALIGNMENT_FIELDS,
        [
            _alignment_row("alignment-1", "aligned", "realistic", a_id),
            _alignment_row("alignment-2", "ambiguous", "realistic", a_id),
        ],
    )
    _write_csv(
        paths["b_alignment"],
        ALIGNMENT_FIELDS,
        [
            _alignment_row(
                "alignment-1",
                "unrelated" if alignment_disagreement else "aligned",
                "realistic",
                b_id,
            ),
            _alignment_row(
                "alignment-2",
                "ambiguous",
                "unrealistic" if alignment_disagreement else "realistic",
                b_id,
            ),
        ],
    )
    audit_manifest = {
        "schema_version": 1,
        "status": "awaiting_two_independent_reviewers_not_training_authorized",
        "review_mode": "dual_ai_engineering",
        "risk_rows": 2,
        "alignment_rows": 2,
        "formal_training_authorized": False,
        "sealed_seed_labels": {"path": "sealed_seed_labels.json", "sha256": "0" * 64},
        "sheets": {
            "reviewer_a_risk.csv": {"rows": 2, "sha256": "0" * 64, "labels_exposed": False},
            "reviewer_b_risk.csv": {"rows": 2, "sha256": "0" * 64, "labels_exposed": False},
            "reviewer_a_alignment.csv": {"rows": 2, "sha256": "0" * 64, "labels_exposed": False},
            "reviewer_b_alignment.csv": {"rows": 2, "sha256": "0" * 64, "labels_exposed": False},
        },
    }
    audit_manifest["sha256"] = hashlib.sha256(
        json.dumps(
            audit_manifest,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    paths["audit_manifest"].write_text(
        json.dumps(audit_manifest, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    paths["ai_manifest"].write_text(
        json.dumps(
            {
                "schema_version": 1,
                "protocol_version": "2.1.0-ai-draft.1",
                "review_mode": "dual_ai_engineering",
                "content_class": "synthetic_project_owned",
                "supplementary_evidence_only": True,
                "human_verified": False,
                "formal_training_authorized": False,
                "audit_manifest_sha256": file_sha256(paths["audit_manifest"]),
                "reviewers": {
                    "ai_a": {
                        "reviewer_id": a_id,
                        "raw_output_files": {
                            "risk_path": paths["a_risk"].name,
                            "risk_sha256": file_sha256(paths["a_risk"]),
                            "alignment_path": paths["a_alignment"].name,
                            "alignment_sha256": file_sha256(paths["a_alignment"]),
                        },
                    },
                    "ai_b": {
                        "reviewer_id": b_id,
                        "raw_output_files": {
                            "risk_path": paths["b_risk"].name,
                            "risk_sha256": file_sha256(paths["b_risk"]),
                            "alignment_path": paths["b_alignment"].name,
                            "alignment_sha256": file_sha256(paths["b_alignment"]),
                        },
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    analysis = {
        "schema_version": 1,
        "protocol_version": "2.1.0-ai-draft.1",
        "review_mode": "dual_ai_engineering",
        "evidence_status": "ai_reviewed_engineering_only",
        "status": "ai_quality_gates_failed_engineering_only",
        "quality_gates_passed": False,
        "human_verified": False,
        "formal_training_authorized": False,
        "ai_review_manifest": {
            "path": str(paths["ai_manifest"].resolve()),
            "sha256": file_sha256(paths["ai_manifest"]),
        },
        "audit_manifest": {
            "path": str(paths["audit_manifest"].resolve()),
            "sha256": file_sha256(paths["audit_manifest"]),
            "sealed_sha256": audit_manifest["sha256"],
        },
        "ai_reviewer_ids": {"reviewer_a": a_id, "reviewer_b": b_id},
    }
    paths["analysis"].write_text(
        json.dumps(analysis, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return paths


def test_builds_separate_risk_and_alignment_disagreement_sheets(tmp_path: Path) -> None:
    paths = _prepare_sources(tmp_path)
    package = tmp_path / "package"

    result = build_package(
        reviewer_a_risk=paths["a_risk"],
        reviewer_b_risk=paths["b_risk"],
        reviewer_a_alignment=paths["a_alignment"],
        reviewer_b_alignment=paths["b_alignment"],
        audit_manifest=paths["audit_manifest"],
        ai_review_manifest=paths["ai_manifest"],
        ai_review_analysis=paths["analysis"],
        output_dir=package,
    )

    manifest = result["manifest"]
    assert manifest["disagreement_counts"] == {"risk": 1, "alignment": 2, "total": 3}
    assert manifest["human_verified"] is False
    assert manifest["constraints"]["this_package_satisfies_independent_human_blind_gate"] is False
    with (package / "risk_disagreement_adjudication.csv").open(encoding="utf-8-sig", newline="") as handle:
        assert len(list(csv.DictReader(handle))) == 1
    with (package / "alignment_disagreement_adjudication.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        assert len(list(csv.DictReader(handle))) == 2


def test_build_rejects_mismatched_provenance_bundle(tmp_path: Path) -> None:
    paths = _prepare_sources(tmp_path)
    wrong_audit = tmp_path / "wrong_audit_manifest.json"
    wrong_audit.write_text(paths["audit_manifest"].read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(ValueError, match="AI review analysis audit_manifest path"):
        build_package(
            reviewer_a_risk=paths["a_risk"],
            reviewer_b_risk=paths["b_risk"],
            reviewer_a_alignment=paths["a_alignment"],
            reviewer_b_alignment=paths["b_alignment"],
            audit_manifest=wrong_audit,
            ai_review_manifest=paths["ai_manifest"],
            ai_review_analysis=paths["analysis"],
            output_dir=tmp_path / "package",
        )


def test_build_rejects_invalid_ai_label_vocabulary(tmp_path: Path) -> None:
    paths = _prepare_sources(tmp_path)
    with paths["a_risk"].open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["risk_label_review"] = "not_a_task_shield_label"
    _write_csv(paths["a_risk"], RISK_FIELDS, rows)
    with pytest.raises(ValueError, match="exact five-label vocabulary"):
        build_package(
            reviewer_a_risk=paths["a_risk"],
            reviewer_b_risk=paths["b_risk"],
            reviewer_a_alignment=paths["a_alignment"],
            reviewer_b_alignment=paths["b_alignment"],
            audit_manifest=paths["audit_manifest"],
            ai_review_manifest=paths["ai_manifest"],
            ai_review_analysis=paths["analysis"],
            output_dir=tmp_path / "package",
        )


def test_build_rejects_analysis_that_claims_quality_gates_passed(tmp_path: Path) -> None:
    paths = _prepare_sources(tmp_path)
    analysis = json.loads(paths["analysis"].read_text(encoding="utf-8"))
    analysis["quality_gates_passed"] = True
    paths["analysis"].write_text(
        json.dumps(analysis, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="quality_gates_passed must be false"):
        build_package(
            reviewer_a_risk=paths["a_risk"],
            reviewer_b_risk=paths["b_risk"],
            reviewer_a_alignment=paths["a_alignment"],
            reviewer_b_alignment=paths["b_alignment"],
            audit_manifest=paths["audit_manifest"],
            ai_review_manifest=paths["ai_manifest"],
            ai_review_analysis=paths["analysis"],
            output_dir=tmp_path / "package",
        )


def test_validate_accepts_a_single_task_disagreement_side(tmp_path: Path) -> None:
    paths = _prepare_sources(tmp_path, alignment_disagreement=False)
    package = tmp_path / "package"
    result = build_package(
        reviewer_a_risk=paths["a_risk"],
        reviewer_b_risk=paths["b_risk"],
        reviewer_a_alignment=paths["a_alignment"],
        reviewer_b_alignment=paths["b_alignment"],
        audit_manifest=paths["audit_manifest"],
        ai_review_manifest=paths["ai_manifest"],
        ai_review_analysis=paths["analysis"],
        output_dir=package,
    )
    assert result["manifest"]["disagreement_counts"] == {"risk": 1, "alignment": 0, "total": 1}
    with (package / "risk_disagreement_adjudication.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["final_risk_label"] = "instruction_hijacking"
        row["adjudication_status"] = "completed_project_owner"
        row["adjudicator_id"] = "owner-01"
        row["adjudicated_at"] = "2026-08-31T13:00:00+08:00"
        row["rationale"] = "Owner reviewed the preserved AI disagreement."
    _write_csv(package / "risk_disagreement_adjudication.csv", RISK_OUTPUT_FIELDS, rows)
    receipt = validate_package(package)
    assert receipt["receipt"]["disagreement_counts"] == {"risk": 1, "alignment": 0, "total": 1}


def test_validate_rejects_changed_outer_evidence(tmp_path: Path) -> None:
    paths = _prepare_sources(tmp_path)
    package = tmp_path / "package"
    build_package(
        reviewer_a_risk=paths["a_risk"],
        reviewer_b_risk=paths["b_risk"],
        reviewer_a_alignment=paths["a_alignment"],
        reviewer_b_alignment=paths["b_alignment"],
        audit_manifest=paths["audit_manifest"],
        ai_review_manifest=paths["ai_manifest"],
        ai_review_analysis=paths["analysis"],
        output_dir=package,
    )
    analysis = json.loads(paths["analysis"].read_text(encoding="utf-8"))
    analysis["limitations"] = ["changed after package creation"]
    paths["analysis"].write_text(
        json.dumps(analysis, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="source evidence changed for ai_review_analysis"):
        validate_package(package)


def test_validate_requires_owner_decisions_and_writes_non_authorizing_receipt(tmp_path: Path) -> None:
    paths = _prepare_sources(tmp_path)
    package = tmp_path / "package"
    build_package(
        reviewer_a_risk=paths["a_risk"],
        reviewer_b_risk=paths["b_risk"],
        reviewer_a_alignment=paths["a_alignment"],
        reviewer_b_alignment=paths["b_alignment"],
        audit_manifest=paths["audit_manifest"],
        ai_review_manifest=paths["ai_manifest"],
        ai_review_analysis=paths["analysis"],
        output_dir=package,
    )
    with pytest.raises(ValueError, match="invalid final Risk label"):
        validate_package(package)

    for filename, fields in (
        ("risk_disagreement_adjudication.csv", RISK_OUTPUT_FIELDS),
        ("alignment_disagreement_adjudication.csv", ALIGNMENT_OUTPUT_FIELDS),
    ):
        path = package / filename
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        for row in rows:
            if filename.startswith("risk"):
                row["final_risk_label"] = "ambiguous"  # intentionally invalid for the Risk schema
            else:
                row["final_task_alignment_label"] = "ambiguous"
                row["final_action_realism"] = "realistic"
            row["adjudication_status"] = "completed_project_owner"
            row["adjudicator_id"] = "owner-01"
            row["adjudicated_at"] = "2026-08-31T13:00:00+08:00"
            row["rationale"] = "Owner reviewed the preserved AI disagreement."
        if filename.startswith("risk"):
            for row in rows:
                row["final_risk_label"] = "instruction_hijacking"
        _write_csv(path, fields, rows)

    receipt = tmp_path / "receipt.json"
    result = validate_package(package, receipt)
    assert result["receipt"]["human_verified"] is False
    assert result["receipt"]["formal_training_authorized"] is False
    assert receipt.is_file()
