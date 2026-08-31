from __future__ import annotations

import csv
import json
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from intentfence.c2b_authorization import validate_c2b_training_authorization
from intentfence.data import file_sha256
from intentfence.route_b import load_route_b_policy
from intentfence.route_b_audit import build_blind_audit_package
from intentfence.route_b_audit_analysis import analyze_blind_audits
from intentfence.route_b_corpus import (
    load_mock_corpus_spec,
    write_formal_mock_corpus,
)
from intentfence.route_b_readiness import (
    build_route_b_protocol_lock,
    evaluate_route_b_readiness,
)

ROOT = Path(__file__).resolve().parents[1]


def _fill_review(path: Path, truth: dict, *, reviewer: str, task: str) -> None:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames
        rows = list(reader)
    truth_by_id = {row["audit_id"]: row for row in truth[task]}
    for row in rows:
        expected = truth_by_id[row["audit_id"]]
        if task == "risk":
            row["risk_label_review"] = expected["seed_risk_label"]
        else:
            row["task_alignment_label_review"] = expected[
                "seed_task_alignment_label"
            ]
            row["action_realism_review"] = "realistic"
        row["review_status"] = "completed"
        row["reviewer"] = reviewer
        row["reviewed_at"] = "2026-08-25T10:00:00+08:00"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _attest(audit_dir: Path, *, reviewer_slot: str, reviewer: str) -> None:
    path = audit_dir / f"{reviewer_slot}_attestation.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.update(
        reviewer_id=reviewer,
        reviewer_kind="independent_human",
        independence_declared=True,
        attested_at="2026-08-25T10:05:00+08:00",
    )
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _fixture(tmp_path: Path) -> dict[str, Path]:
    spec = deepcopy(load_mock_corpus_spec(ROOT / "configs" / "route_b_mock_corpus.yaml"))
    for role in spec["roles"].values():
        role["template_groups"] = 5
    candidate_dir = tmp_path / "candidate"
    result = write_formal_mock_corpus(spec, candidate_dir)
    manifest = result["manifest"]

    policy = load_route_b_policy(ROOT / "configs" / "route_b_data_protocol.yaml")
    policy.update(
        protocol_version="2.0.0",
        status="frozen",
        approved_by="project_owner",
        approved_at="2026-08-25T10:30:00+08:00",
    )
    policy["sample_size"]["status"] = "frozen"
    policy["readiness"]["formal_training_authorized"] = True
    policy["readiness"]["public_aggregate_reports_complete"] = True
    policy_path = tmp_path / "route_b_policy.yaml"
    policy_path.write_text(yaml.safe_dump(policy, sort_keys=False), encoding="utf-8")

    protocol_document = tmp_path / "route_b_protocol.md"
    protocol_document.write_text("# Frozen Route B protocol 2.0.0\n", encoding="utf-8")
    lock = build_route_b_protocol_lock(
        policy_path=policy_path,
        protocol_document=protocol_document,
    )
    lock_path = tmp_path / "route_b_protocol_lock.json"
    lock_path.write_text(json.dumps(lock, sort_keys=True), encoding="utf-8")

    integrity = {
        "errors": [],
        "warnings": [],
        "near_duplicate_check_performed": True,
        "near_threshold": policy["split_isolation"]["near_duplicate_threshold"],
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
                "path": str(policy_path),
                "sha256": file_sha256(policy_path),
            },
            "inputs": [
                {
                    "path": str(candidate_dir / evidence["path"]),
                    "sha256": evidence["sha256"],
                }
                for evidence in manifest["splits"].values()
            ],
        },
    }
    integrity_path = candidate_dir / "integrity.json"
    integrity_path.write_text(json.dumps(integrity), encoding="utf-8")

    inputs = [candidate_dir / f"{role}.jsonl" for role in manifest["splits"]]
    audit_dir = tmp_path / "audit"
    build_blind_audit_package(inputs, audit_dir, risk_rows=400, alignment_rows=400)
    truth = json.loads((audit_dir / "sealed_seed_labels.json").read_text(encoding="utf-8"))
    for slot, reviewer in (("reviewer_a", "human_a"), ("reviewer_b", "human_b")):
        _fill_review(audit_dir / f"{slot}_risk.csv", truth, reviewer=reviewer, task="risk")
        _fill_review(
            audit_dir / f"{slot}_alignment.csv",
            truth,
            reviewer=reviewer,
            task="alignment",
        )
        _attest(audit_dir, reviewer_slot=slot, reviewer=reviewer)
    analysis = analyze_blind_audits(
        reviewer_a_risk=audit_dir / "reviewer_a_risk.csv",
        reviewer_b_risk=audit_dir / "reviewer_b_risk.csv",
        reviewer_a_alignment=audit_dir / "reviewer_a_alignment.csv",
        reviewer_b_alignment=audit_dir / "reviewer_b_alignment.csv",
        sealed_seed_labels=audit_dir / "sealed_seed_labels.json",
        audit_manifest=audit_dir / "audit_manifest.json",
        policy=policy,
    )
    analysis_path = audit_dir / "audit_analysis.json"
    analysis_path.write_text(json.dumps(analysis, sort_keys=True), encoding="utf-8")
    public_report = tmp_path / "route_b_card.md"
    public_report.write_text(
        "Manifest sealed SHA-256: `"
        + manifest["sha256"]
        + "`\nStatus: READY_FOR_PROJECT_OWNER_TRAINING\n",
        encoding="utf-8",
    )
    return {
        "policy_path": policy_path,
        "protocol_document": protocol_document,
        "protocol_lock": lock_path,
        "candidate_manifest": candidate_dir / "manifest.json",
        "integrity_report": integrity_path,
        "audit_analysis": analysis_path,
        "audit_manifest": audit_dir / "audit_manifest.json",
        "public_report": public_report,
    }


def test_complete_evidence_opens_only_project_owner_training_gate(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    report = evaluate_route_b_readiness(**paths)
    assert report["status"] == "ready_for_project_owner_training"
    assert report["formal_training_authorized"] is True
    assert report["training_executor"] == "project_owner_only"
    assert report["final_test_lock_remains_active"] is True
    assert report["readiness_blockers"] == []
    assert report["validation_errors"] == []


def test_missing_human_audit_and_protocol_lock_fail_closed(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    paths["audit_analysis"] = None
    paths["audit_manifest"] = None
    paths["protocol_lock"] = None
    report = evaluate_route_b_readiness(**paths)
    assert report["status"] == "readiness_blocked"
    assert report["formal_training_authorized"] is False
    assert report["gates"]["independent_human_audit_quality_gates_passed"] is False
    assert report["gates"]["protocol_2_0_0_approved_and_frozen"] is False


def test_protocol_lock_detects_policy_drift(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    with paths["policy_path"].open("a", encoding="utf-8") as handle:
        handle.write("# drift\n")
    report = evaluate_route_b_readiness(**paths)
    assert report["formal_training_authorized"] is False
    assert any("protocol lock file hash mismatch" in item for item in report["validation_errors"])


def test_ai_review_mode_cannot_satisfy_human_audit_gate(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    analysis = json.loads(paths["audit_analysis"].read_text(encoding="utf-8"))
    analysis["review_mode"] = "dual_ai_engineering"
    paths["audit_analysis"].write_text(json.dumps(analysis, sort_keys=True), encoding="utf-8")
    report = evaluate_route_b_readiness(**paths)
    assert report["formal_training_authorized"] is False
    assert any("not an independent human blind review" in item for item in report["validation_errors"])


def test_public_report_must_bind_candidate_manifest(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    paths["public_report"].write_text(
        "Manifest sealed SHA-256: `" + "0" * 64 + "`\n",
        encoding="utf-8",
    )
    report = evaluate_route_b_readiness(**paths)
    assert report["formal_training_authorized"] is False
    assert report["gates"]["v2_manifest_and_public_aggregate_reports_complete"] is False
    assert any(
        "public aggregate report does not bind the candidate manifest sealed SHA-256" in item
        for item in report["validation_errors"]
    )


def _c2b_authorization_fixture(tmp_path: Path) -> dict[str, Path | str]:
    paths = _fixture(tmp_path)
    candidate_id = json.loads(paths["candidate_manifest"].read_text(encoding="utf-8"))["data_version"]
    readiness = evaluate_route_b_readiness(**paths)
    readiness_path = tmp_path / "readiness.json"
    readiness_path.write_text(json.dumps(readiness, sort_keys=True), encoding="utf-8")
    authorization_path = tmp_path / "training_authorization.json"
    authorization_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "candidate_id": candidate_id,
                "protocol_version": "2.0.0",
                "human_verified": True,
                "formal_training_authorized": True,
                "approved_by_project_owner": "owner-test",
                "approved_at": "2026-08-25T10:30:00+08:00",
                "candidate_manifest_sha256": file_sha256(paths["candidate_manifest"]),
                "readiness_report_sha256": file_sha256(readiness_path),
                "protocol_lock_sha256": file_sha256(paths["protocol_lock"]),
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return {
        "authorization_path": authorization_path,
        "expected_candidate": candidate_id,
        "candidate_manifest_path": paths["candidate_manifest"],
        "train_path": paths["candidate_manifest"].parent / "train.jsonl",
        "validation_path": paths["candidate_manifest"].parent / "validation.jsonl",
        "readiness_report_path": readiness_path,
        "protocol_lock_path": paths["protocol_lock"],
        "policy_path": paths["policy_path"],
        "protocol_document_path": paths["protocol_document"],
        "integrity_report_path": paths["integrity_report"],
        "audit_analysis_path": paths["audit_analysis"],
        "audit_manifest_path": paths["audit_manifest"],
        "public_report_path": paths["public_report"],
    }


def test_c2b_authorization_requires_replayable_frozen_evidence(tmp_path: Path) -> None:
    paths = _c2b_authorization_fixture(tmp_path)

    result = validate_c2b_training_authorization(**paths)

    assert result["status"] == "c2b_training_authorization_validated"
    assert result["protocol_version"] == "2.0.0"


def test_c2b_authorization_rejects_legacy_protocol_version(tmp_path: Path) -> None:
    paths = _c2b_authorization_fixture(tmp_path)
    authorization = json.loads(paths["authorization_path"].read_text(encoding="utf-8"))
    authorization["protocol_version"] = "1.0.0"
    paths["authorization_path"].write_text(
        json.dumps(authorization, sort_keys=True), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="protocol_version must be 2.0.0"):
        validate_c2b_training_authorization(**paths)


def test_c2b_authorization_rejects_readiness_drift(tmp_path: Path) -> None:
    paths = _c2b_authorization_fixture(tmp_path)
    readiness = json.loads(paths["readiness_report_path"].read_text(encoding="utf-8"))
    readiness["formal_training_authorized"] = False
    paths["readiness_report_path"].write_text(
        json.dumps(readiness, sort_keys=True), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="readiness report does not authorize"):
        validate_c2b_training_authorization(**paths)


def test_c2b_authorization_rejects_unbound_training_input(tmp_path: Path) -> None:
    paths = _c2b_authorization_fixture(tmp_path)
    alternate_train = tmp_path / "alternate_train.jsonl"
    alternate_train.write_bytes(paths["train_path"].read_bytes())
    paths["train_path"] = alternate_train

    with pytest.raises(ValueError, match="training train path does not match"):
        validate_c2b_training_authorization(**paths)


def test_c2b_authorization_rejects_candidate_manifest_mismatch(tmp_path: Path) -> None:
    paths = _c2b_authorization_fixture(tmp_path)
    authorization = json.loads(paths["authorization_path"].read_text(encoding="utf-8"))
    authorization["candidate_id"] = "route_b_v2_candidate_other"
    paths["authorization_path"].write_text(
        json.dumps(authorization, sort_keys=True), encoding="utf-8"
    )
    paths["expected_candidate"] = "route_b_v2_candidate_other"

    with pytest.raises(ValueError, match="candidate manifest data_version"):
        validate_c2b_training_authorization(**paths)
