from __future__ import annotations

import csv
import json
from copy import deepcopy
from pathlib import Path

from intentfence.route_b import load_route_b_policy
from intentfence.route_b_audit import build_blind_audit_package
from intentfence.route_b_audit_analysis import analyze_blind_audits
from intentfence.route_b_corpus import build_formal_mock_records, load_mock_corpus_spec
from intentfence.schema import write_jsonl

ROOT = Path(__file__).resolve().parents[1]


def _package(tmp_path: Path) -> Path:
    spec = deepcopy(load_mock_corpus_spec(ROOT / "configs" / "route_b_mock_corpus.yaml"))
    for role in spec["roles"].values():
        role["template_groups"] = 2
    records, _ = build_formal_mock_records(spec)
    inputs = []
    for role, rows in records.items():
        path = tmp_path / f"{role}.jsonl"
        write_jsonl(rows, path)
        inputs.append(path)
    output = tmp_path / "audit"
    build_blind_audit_package(inputs, output, risk_rows=40, alignment_rows=80)
    return output


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
        row["reviewed_at"] = "2026-08-24T21:00:00+08:00"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _attest(package: Path, *, reviewer_slot: str, reviewer: str) -> None:
    path = package / f"{reviewer_slot}_attestation.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.update(
        reviewer_id=reviewer,
        reviewer_kind="independent_human",
        independence_declared=True,
        attested_at="2026-08-24T21:05:00+08:00",
    )
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def test_completed_blind_reviews_pass_preregistered_gates(tmp_path: Path) -> None:
    package = _package(tmp_path)
    import json

    truth = json.loads((package / "sealed_seed_labels.json").read_text(encoding="utf-8"))
    for slot, reviewer in (("reviewer_a", "human_a"), ("reviewer_b", "human_b")):
        _fill(package / f"{slot}_risk.csv", truth, reviewer=reviewer, task="risk")
        _fill(
            package / f"{slot}_alignment.csv",
            truth,
            reviewer=reviewer,
            task="alignment",
        )
        _attest(package, reviewer_slot=slot, reviewer=reviewer)
    report = analyze_blind_audits(
        reviewer_a_risk=package / "reviewer_a_risk.csv",
        reviewer_b_risk=package / "reviewer_b_risk.csv",
        reviewer_a_alignment=package / "reviewer_a_alignment.csv",
        reviewer_b_alignment=package / "reviewer_b_alignment.csv",
        sealed_seed_labels=package / "sealed_seed_labels.json",
        audit_manifest=package / "audit_manifest.json",
        policy=load_route_b_policy(ROOT / "configs" / "route_b_data_protocol.yaml"),
    )
    assert report["status"] == "quality_gates_passed"
    assert report["quality_gates_passed"] is True
    assert report["formal_training_authorized"] is False


def test_modified_review_scenario_is_rejected(tmp_path: Path) -> None:
    package = _package(tmp_path)
    import json

    truth = json.loads((package / "sealed_seed_labels.json").read_text(encoding="utf-8"))
    for slot, reviewer in (("reviewer_a", "human_a"), ("reviewer_b", "human_b")):
        _fill(package / f"{slot}_risk.csv", truth, reviewer=reviewer, task="risk")
        _fill(
            package / f"{slot}_alignment.csv",
            truth,
            reviewer=reviewer,
            task="alignment",
        )
        _attest(package, reviewer_slot=slot, reviewer=reviewer)
    path = package / "reviewer_b_risk.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames
        rows = list(reader)
    rows[0]["scenario"] += " modified"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    report = analyze_blind_audits(
        reviewer_a_risk=package / "reviewer_a_risk.csv",
        reviewer_b_risk=path,
        reviewer_a_alignment=package / "reviewer_a_alignment.csv",
        reviewer_b_alignment=package / "reviewer_b_alignment.csv",
        sealed_seed_labels=package / "sealed_seed_labels.json",
        audit_manifest=package / "audit_manifest.json",
        policy=load_route_b_policy(ROOT / "configs" / "route_b_data_protocol.yaml"),
    )
    assert report["status"] == "invalid_review_package"
    assert any("immutable review content was modified" in error for error in report["validation_errors"])


def test_missing_human_attestation_is_rejected(tmp_path: Path) -> None:
    package = _package(tmp_path)
    truth = json.loads((package / "sealed_seed_labels.json").read_text(encoding="utf-8"))
    for slot, reviewer in (("reviewer_a", "human_a"), ("reviewer_b", "human_b")):
        _fill(package / f"{slot}_risk.csv", truth, reviewer=reviewer, task="risk")
        _fill(
            package / f"{slot}_alignment.csv",
            truth,
            reviewer=reviewer,
            task="alignment",
        )
    report = analyze_blind_audits(
        reviewer_a_risk=package / "reviewer_a_risk.csv",
        reviewer_b_risk=package / "reviewer_b_risk.csv",
        reviewer_a_alignment=package / "reviewer_a_alignment.csv",
        reviewer_b_alignment=package / "reviewer_b_alignment.csv",
        sealed_seed_labels=package / "sealed_seed_labels.json",
        audit_manifest=package / "audit_manifest.json",
        policy=load_route_b_policy(ROOT / "configs" / "route_b_data_protocol.yaml"),
    )
    assert report["status"] == "invalid_review_package"
    assert any("independence declaration is missing" in item for item in report["validation_errors"])
