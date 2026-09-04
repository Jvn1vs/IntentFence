from __future__ import annotations

import csv
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from intentfence.c2b_authorization import validate_c2b_training_authorization
from intentfence.data import file_sha256
from intentfence.route_b import load_route_b_policy
from intentfence.route_b_ai_review import analyze_dual_ai_reviews
from intentfence.route_b_ai_training import (
    AI_TRAINING_PROTOCOL_VERSION,
    _ai_review_evidence_gate,
    _same_path,
    build_ai_training_protocol_lock,
    build_ai_training_readiness,
)
from intentfence.route_b_audit import build_blind_audit_package
from intentfence.route_b_corpus import load_mock_corpus_spec, write_formal_mock_corpus

ROOT = Path(__file__).resolve().parents[1]


def _fill_review(
    path: Path,
    truth: dict[str, list[dict[str, str]]],
    *,
    reviewer: str,
    task: str,
    introduce_disagreement: bool = False,
) -> None:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames
        rows = list(reader)
    truth_by_id = {row["audit_id"]: row for row in truth[task]}
    for index, row in enumerate(rows):
        expected = truth_by_id[row["audit_id"]]
        if task == "risk":
            label = expected["seed_risk_label"]
            if introduce_disagreement and index == 0:
                label = "tool_manipulation" if label != "tool_manipulation" else "benign"
            row["risk_label_review"] = label
        else:
            row["task_alignment_label_review"] = expected["seed_task_alignment_label"]
            row["action_realism_review"] = "realistic"
        row["review_status"] = "completed"
        row["reviewer"] = reviewer
        row["reviewed_at"] = "2026-09-04T16:00:00+08:00"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _fixture(tmp_path: Path, *, ai_failure: bool = False) -> dict[str, Path | str]:
    spec = deepcopy(load_mock_corpus_spec(ROOT / "configs" / "route_b_mock_corpus.yaml"))
    spec["data_version"] = "route_b_ai_training_test"
    for role in spec["roles"].values():
        role["template_groups"] = 5
    candidate_dir = tmp_path / "candidate"
    result = write_formal_mock_corpus(spec, candidate_dir)
    manifest = result["manifest"]
    candidate_manifest_path = candidate_dir / "manifest.json"

    data_policy = load_route_b_policy(ROOT / "configs" / "route_b_data_protocol.yaml")
    data_policy_path = tmp_path / "data_protocol.yaml"
    data_policy_path.write_text(
        yaml.safe_dump(data_policy, sort_keys=False), encoding="utf-8"
    )
    new_policy = load_route_b_policy(
        ROOT / "configs" / "route_b_ai_training_protocol.yaml"
    )
    new_policy["audit"]["sample_rows"] = {"risk": 40, "alignment": 80}
    new_policy["readiness"]["public_aggregate_reports_complete"] = True
    new_policy_path = tmp_path / "ai_training_protocol.yaml"
    new_policy_path.write_text(
        yaml.safe_dump(new_policy, sort_keys=False), encoding="utf-8"
    )
    ai_policy = load_route_b_policy(ROOT / "configs" / "route_b_ai_review_protocol.yaml")
    ai_policy["audit"]["sample_rows"] = {"risk": 40, "alignment": 80}
    ai_policy_path = tmp_path / "ai_review_protocol.yaml"
    ai_policy_path.write_text(
        yaml.safe_dump(ai_policy, sort_keys=False), encoding="utf-8"
    )
    protocol_document_path = tmp_path / "ai_training_protocol.md"
    protocol_document_path.write_text("# AI engineering protocol fixture\n", encoding="utf-8")
    lock = build_ai_training_protocol_lock(
        policy_path=new_policy_path,
        protocol_document=protocol_document_path,
        integrity_policy_path=data_policy_path,
        ai_review_policy_path=ai_policy_path,
    )
    lock_path = tmp_path / "ai_training_protocol_lock.json"
    lock_path.write_text(json.dumps(lock, sort_keys=True), encoding="utf-8")

    integrity = {
        "errors": [],
        "near_duplicate_check_performed": True,
        "near_threshold": data_policy["split_isolation"]["near_duplicate_threshold"],
        "summary": {
            "by_split": {
                role: manifest["splits"][role]["rows"]
                for role in sorted(manifest["splits"])
            },
            "risk_alignment_mutual_information_bits": 0.0,
            "template_representative_near_integrity": {"representatives": 400},
        },
        "evidence": {
            "config": {
                "path": str(data_policy_path),
                "sha256": file_sha256(data_policy_path),
            },
            "inputs": [
                {
                    "path": str(candidate_dir / item["path"]),
                    "sha256": item["sha256"],
                }
                for item in manifest["splits"].values()
            ],
        },
    }
    integrity_path = candidate_dir / "integrity.json"
    integrity_path.write_text(json.dumps(integrity), encoding="utf-8")

    audit_dir = tmp_path / "ai_audit"
    input_paths = [
        candidate_dir / f"{role}.jsonl"
        for role in ("train", "validation", "calibration", "test_a")
    ]
    build_blind_audit_package(
        input_paths,
        audit_dir,
        risk_rows=40,
        alignment_rows=80,
        seed=42,
        review_mode="dual_ai_engineering",
    )
    truth = json.loads((audit_dir / "sealed_seed_labels.json").read_text(encoding="utf-8"))
    for slot, reviewer in (
        ("reviewer_a", "provider-a:model-a@revision-a"),
        ("reviewer_b", "provider-b:model-b@revision-b"),
    ):
        _fill_review(
            audit_dir / f"{slot}_risk.csv",
            truth,
            reviewer=reviewer,
            task="risk",
            introduce_disagreement=ai_failure and slot == "reviewer_b",
        )
        _fill_review(
            audit_dir / f"{slot}_alignment.csv",
            truth,
            reviewer=reviewer,
            task="alignment",
        )
    ai_manifest = {
        "schema_version": 1,
        "protocol_version": "2.1.0-ai-draft.1",
        "review_mode": "dual_ai_engineering",
        "content_class": "synthetic_project_owned",
        "external_upload_approved_by_project_owner": False,
        "audit_manifest_sha256": file_sha256(audit_dir / "audit_manifest.json"),
        "reviewers": {},
    }
    for slot, provider, model, revision in (
        ("ai_a", "provider-a", "model-a", "revision-a"),
        ("ai_b", "provider-b", "model-b", "revision-b"),
    ):
        prefix = "reviewer_a" if slot == "ai_a" else "reviewer_b"
        ai_manifest["reviewers"][slot] = {
            "reviewer_id": f"{provider}:{model}@{revision}",
            "provider": provider,
            "model": model,
            "revision": revision,
            "execution_mode": "local",
            "temperature": 0,
            "prompt_sha256": hashlib.sha256(slot.encode()).hexdigest(),
            "seed_labels_hidden": True,
            "other_reviewer_output_hidden": True,
            "raw_output_files": {
                "risk_path": f"{prefix}_risk.csv",
                "risk_sha256": file_sha256(audit_dir / f"{prefix}_risk.csv"),
                "alignment_path": f"{prefix}_alignment.csv",
                "alignment_sha256": file_sha256(audit_dir / f"{prefix}_alignment.csv"),
            },
        }
    ai_manifest_path = audit_dir / "ai_review_manifest.json"
    ai_manifest_path.write_text(
        json.dumps(ai_manifest, sort_keys=True), encoding="utf-8"
    )
    analysis = analyze_dual_ai_reviews(
        reviewer_a_risk=audit_dir / "reviewer_a_risk.csv",
        reviewer_b_risk=audit_dir / "reviewer_b_risk.csv",
        reviewer_a_alignment=audit_dir / "reviewer_a_alignment.csv",
        reviewer_b_alignment=audit_dir / "reviewer_b_alignment.csv",
        sealed_seed_labels=audit_dir / "sealed_seed_labels.json",
        audit_manifest=audit_dir / "audit_manifest.json",
        ai_review_manifest=ai_manifest_path,
        policy=ai_policy,
    )
    analysis_path = audit_dir / "ai_review_analysis.json"
    analysis_path.write_text(json.dumps(analysis, sort_keys=True), encoding="utf-8")

    public_report_path = tmp_path / "ai_engineering_card.md"
    public_report_path.write_text(
        f"Manifest sealed SHA-256: {chr(96)}{manifest['sha256']}{chr(96)}\n",
        encoding="utf-8",
    )
    readiness = build_ai_training_readiness(
        policy_path=new_policy_path,
        protocol_document=protocol_document_path,
        protocol_lock=lock_path,
        candidate_manifest=candidate_manifest_path,
        integrity_report=integrity_path,
        ai_review_analysis=analysis_path,
        ai_review_manifest=ai_manifest_path,
        audit_manifest=audit_dir / "audit_manifest.json",
        public_report=public_report_path,
        integrity_policy_path=data_policy_path,
        ai_review_policy_path=ai_policy_path,
    )
    readiness_path = tmp_path / "ai_engineering_readiness.json"
    readiness_path.write_text(json.dumps(readiness, sort_keys=True), encoding="utf-8")
    candidate_id = manifest["data_version"]
    authorization_path = tmp_path / "ai_training_authorization.json"
    authorization = {
        "schema_version": 1,
        "candidate_id": candidate_id,
        "protocol_version": AI_TRAINING_PROTOCOL_VERSION,
        "training_authorization_mode": "ai_reviewed_engineering",
        "human_verified": False,
        "formal_training_authorized": False,
        "engineering_training_authorized": True,
        "training_executor": "project_owner_only",
        "ai_evidence_class": "ai_reviewed_engineering_only",
        "ai_quality_gate_failure_accepted": ai_failure,
        "approved_by_project_owner": "owner-test",
        "approved_at": "2026-09-04T16:05:00+08:00",
        "final_test_lock_remains_active": True,
        "calibration_lock_remains_active": True,
        "candidate_manifest_sha256": file_sha256(candidate_manifest_path),
        "readiness_report_sha256": file_sha256(readiness_path),
        "protocol_lock_sha256": file_sha256(lock_path),
        "integrity_policy_sha256": file_sha256(data_policy_path),
        "ai_review_policy_sha256": file_sha256(ai_policy_path),
        "ai_review_analysis_sha256": file_sha256(analysis_path),
        "ai_review_manifest_sha256": file_sha256(ai_manifest_path),
    }
    if ai_failure:
        authorization["ai_quality_gate_failure_reason"] = (
            "Owner accepts exploratory engineering use while preserving the failed AI gates."
        )
    authorization_path.write_text(
        json.dumps(authorization, sort_keys=True), encoding="utf-8"
    )
    return {
        "authorization_path": authorization_path,
        "expected_candidate": candidate_id,
        "candidate_manifest_path": candidate_manifest_path,
        "train_path": candidate_dir / "train.jsonl",
        "validation_path": candidate_dir / "validation.jsonl",
        "readiness_report_path": readiness_path,
        "protocol_lock_path": lock_path,
        "policy_path": new_policy_path,
        "protocol_document_path": protocol_document_path,
        "integrity_report_path": integrity_path,
        "audit_analysis_path": analysis_path,
        "audit_manifest_path": audit_dir / "audit_manifest.json",
        "public_report_path": public_report_path,
        "ai_review_manifest_path": ai_manifest_path,
        "integrity_policy_path": data_policy_path,
        "ai_review_policy_path": ai_policy_path,
        "readiness": readiness,
    }


def _authorization_args(paths: dict[str, Path | str]) -> dict[str, Path | str]:
    return {key: value for key, value in paths.items() if key != "readiness"}


def test_ai_route_accepts_owner_authorized_engineering_training(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    assert paths["readiness"]["status"] == "eligible_for_owner_ai_engineering_authorization"
    assert paths["readiness"]["engineering_training_eligible"] is True
    assert paths["readiness"]["ai_quality_gates_passed"] is True

    result = validate_c2b_training_authorization(**_authorization_args(paths))

    assert result["status"] == "c2b_ai_engineering_training_authorization_validated"
    assert result["human_verified"] is False
    assert result["formal_training_authorized"] is False
    assert result["engineering_training_authorized"] is True


def test_ai_route_accepts_readiness_relocated_to_another_host(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    readiness_path = paths["readiness_report_path"]
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    for index, binding in enumerate(readiness["evidence"].values()):
        binding["path"] = f"C:\\legacy\\IntentFence\\evidence-{index}.json"
    readiness_path.write_text(json.dumps(readiness, sort_keys=True), encoding="utf-8")

    authorization_path = paths["authorization_path"]
    authorization = json.loads(authorization_path.read_text(encoding="utf-8"))
    authorization["readiness_report_sha256"] = file_sha256(readiness_path)
    authorization_path.write_text(json.dumps(authorization, sort_keys=True), encoding="utf-8")

    result = validate_c2b_training_authorization(**_authorization_args(paths))

    assert result["status"] == "c2b_ai_engineering_training_authorization_validated"


def test_ai_review_replay_accepts_relocated_bound_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    analysis_path = paths["audit_analysis_path"]
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    analysis["ai_review_manifest"]["path"] = (
        rf"C:\legacy\{tmp_path.name}\ai_audit\ai_review_manifest.json"
    )
    analysis["audit_manifest"]["path"] = (
        rf"C:\legacy\{tmp_path.name}\ai_audit\audit_manifest.json"
    )
    analysis_path.write_text(json.dumps(analysis, sort_keys=True), encoding="utf-8")

    policy = load_route_b_policy(paths["policy_path"])
    ai_policy = paths["ai_review_policy_path"]
    candidate_manifest = json.loads(
        paths["candidate_manifest_path"].read_text(encoding="utf-8")
    )
    passed, errors, _, _ = _ai_review_evidence_gate(
        analysis_path=analysis_path,
        ai_review_manifest_path=paths["ai_review_manifest_path"],
        audit_manifest_path=paths["audit_manifest_path"],
        candidate_manifest=candidate_manifest,
        policy=policy,
        ai_review_policy_path=ai_policy,
    )

    assert passed, errors


def test_same_path_accepts_relocated_windows_project_path() -> None:
    assert _same_path(
        r"C:\\legacy\\IntentFence\\ai_audit\\ai_review_manifest.json",
        ROOT / "ai_audit" / "ai_review_manifest.json",
    )


def test_ai_route_requires_owner_acceptance_reason_after_failed_quality_gates(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path, ai_failure=True)
    assert paths["readiness"]["ai_quality_gates_passed"] is False
    authorization_path = paths["authorization_path"]
    authorization = json.loads(authorization_path.read_text(encoding="utf-8"))
    authorization.pop("ai_quality_gate_failure_reason")
    authorization_path.write_text(json.dumps(authorization, sort_keys=True), encoding="utf-8")

    with pytest.raises(ValueError, match="non-empty acceptance reason"):
        validate_c2b_training_authorization(**_authorization_args(paths))


def test_ai_route_rejects_human_verified_flag(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    authorization_path = paths["authorization_path"]
    authorization = json.loads(authorization_path.read_text(encoding="utf-8"))
    authorization["human_verified"] = True
    authorization_path.write_text(json.dumps(authorization, sort_keys=True), encoding="utf-8")

    with pytest.raises(ValueError, match="human_verified"):
        validate_c2b_training_authorization(**_authorization_args(paths))


def test_ai_route_rejects_protocol_lock_path_drift(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    lock_path = paths["protocol_lock_path"]
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock["files"]["policy"]["path"] = str(tmp_path / "different-policy.yaml")
    lock_path.write_text(json.dumps(lock, sort_keys=True), encoding="utf-8")

    report = build_ai_training_readiness(
        policy_path=paths["policy_path"],
        protocol_document=paths["protocol_document_path"],
        protocol_lock=lock_path,
        candidate_manifest=paths["candidate_manifest_path"],
        integrity_report=paths["integrity_report_path"],
        ai_review_analysis=paths["audit_analysis_path"],
        ai_review_manifest=paths["ai_review_manifest_path"],
        audit_manifest=paths["audit_manifest_path"],
        public_report=paths["public_report_path"],
        integrity_policy_path=paths["integrity_policy_path"],
        ai_review_policy_path=paths["ai_review_policy_path"],
    )
    assert report["engineering_training_eligible"] is False
    assert any(
        "protocol lock file hash mismatch: policy" in error
        for error in report["validation_errors"]
    )
