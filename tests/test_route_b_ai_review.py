from __future__ import annotations

import csv
import hashlib
import json
from copy import deepcopy
from pathlib import Path

from intentfence.data import file_sha256
from intentfence.route_b import load_route_b_policy
from intentfence.route_b_ai_review import analyze_dual_ai_reviews
from intentfence.route_b_audit import build_blind_audit_package
from intentfence.route_b_corpus import build_formal_mock_records, load_mock_corpus_spec
from intentfence.schema import write_jsonl

ROOT = Path(__file__).resolve().parents[1]


def _fill(path: Path, truth: dict, *, reviewer: str, task: str) -> None:
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
            row["task_alignment_label_review"] = expected["seed_task_alignment_label"]
            row["action_realism_review"] = "realistic"
        row["review_status"] = "completed"
        row["reviewer"] = reviewer
        row["reviewed_at"] = "2026-08-26T10:00:00+08:00"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _fixture(tmp_path: Path) -> dict[str, object]:
    spec = deepcopy(load_mock_corpus_spec(ROOT / "configs" / "route_b_mock_corpus.yaml"))
    for role in spec["roles"].values():
        role["template_groups"] = 2
    records, _ = build_formal_mock_records(spec)
    input_paths = []
    for role, rows in records.items():
        path = tmp_path / f"{role}.jsonl"
        write_jsonl(rows, path)
        input_paths.append(path)
    audit_dir = tmp_path / "audit"
    build_blind_audit_package(input_paths, audit_dir, risk_rows=40, alignment_rows=80)
    truth = json.loads((audit_dir / "sealed_seed_labels.json").read_text(encoding="utf-8"))
    reviewer_ids = {
        "reviewer_a": "provider_a:model_a@revision_a",
        "reviewer_b": "provider_b:model_b@revision_b",
    }
    for slot, reviewer in reviewer_ids.items():
        _fill(audit_dir / f"{slot}_risk.csv", truth, reviewer=reviewer, task="risk")
        _fill(
            audit_dir / f"{slot}_alignment.csv",
            truth,
            reviewer=reviewer,
            task="alignment",
        )
    policy = load_route_b_policy(ROOT / "configs" / "route_b_ai_review_protocol.yaml")
    policy["audit"]["sample_rows"] = {"risk": 40, "alignment": 80}
    metadata = {
        "schema_version": 1,
        "protocol_version": "2.1.0-ai-draft.1",
        "review_mode": "dual_ai_engineering",
        "content_class": "synthetic_project_owned",
        "external_upload_approved_by_project_owner": False,
        "audit_manifest_sha256": file_sha256(audit_dir / "audit_manifest.json"),
        "reviewers": {},
    }
    for slot, provider, model, revision in (
        ("ai_a", "provider_a", "model_a", "revision_a"),
        ("ai_b", "provider_b", "model_b", "revision_b"),
    ):
        prefix = "reviewer_a" if slot == "ai_a" else "reviewer_b"
        metadata["reviewers"][slot] = {
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
    metadata_path = audit_dir / "ai_review_manifest.json"
    metadata_path.write_text(json.dumps(metadata, sort_keys=True), encoding="utf-8")
    return {
        "reviewer_a_risk": audit_dir / "reviewer_a_risk.csv",
        "reviewer_b_risk": audit_dir / "reviewer_b_risk.csv",
        "reviewer_a_alignment": audit_dir / "reviewer_a_alignment.csv",
        "reviewer_b_alignment": audit_dir / "reviewer_b_alignment.csv",
        "sealed_seed_labels": audit_dir / "sealed_seed_labels.json",
        "audit_manifest": audit_dir / "audit_manifest.json",
        "ai_review_manifest": metadata_path,
        "policy": policy,
    }


def test_dual_ai_review_is_engineering_only(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    report = analyze_dual_ai_reviews(**paths)
    assert report["status"] == "ai_quality_gates_passed_engineering_only"
    assert report["evidence_status"] == "ai_reviewed_engineering_only"
    assert report["quality_gates_passed"] is True
    assert report["human_verified"] is False
    assert report["formal_training_authorized"] is False
    assert report["ai_reviewer_models"]["ai_a"]["provider"] != report["ai_reviewer_models"]["ai_b"]["provider"]


def test_dual_ai_rejects_same_model_identity(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    metadata_path = paths["ai_review_manifest"]
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["reviewers"]["ai_b"].update(
        provider=metadata["reviewers"]["ai_a"]["provider"],
        model=metadata["reviewers"]["ai_a"]["model"],
        revision=metadata["reviewers"]["ai_a"]["revision"],
    )
    metadata_path.write_text(json.dumps(metadata, sort_keys=True), encoding="utf-8")
    report = analyze_dual_ai_reviews(**paths)
    assert report["status"] == "invalid_ai_review_package"
    assert any("distinct provider/model/revision" in item for item in report["validation_errors"])
