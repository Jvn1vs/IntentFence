from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from intentfence.constants import RISK_LABELS, TASK_ALIGNMENT_LABELS
from intentfence.data import file_sha256
from intentfence.route_b import load_route_b_policy
from intentfence.route_b_audit_analysis import analyze_blind_audits
from intentfence.route_b_corpus import validate_formal_mock_manifest

CONSTRUCTION_ROLES = ("train", "validation", "calibration", "test_a")
READY_AUDIT_STATUSES = {
    "quality_gates_passed",
    "quality_gates_passed_adjudication_required",
}


def _read_json(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {source}")
    return payload


def _sealed_hash(payload: dict[str, Any]) -> str:
    unsigned = dict(payload)
    unsigned.pop("sha256", None)
    serialized = json.dumps(
        unsigned,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _has_timezone(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def build_route_b_protocol_lock(
    *,
    policy_path: str | Path,
    protocol_document: str | Path,
) -> dict[str, Any]:
    policy_source = Path(policy_path)
    document_source = Path(protocol_document)
    policy = load_route_b_policy(policy_source)
    if policy.get("protocol_version") != "2.0.0" or policy.get("status") != "frozen":
        raise ValueError("Route B protocol must be version 2.0.0 with status=frozen")
    if policy.get("approved_by") != "project_owner" or not _has_timezone(
        policy.get("approved_at")
    ):
        raise ValueError("frozen protocol requires project-owner approval with timezone")
    readiness = policy.get("readiness", {})
    if readiness.get("formal_training_authorized") is not True:
        raise ValueError("project owner has not recorded formal training authorization")
    if readiness.get("public_aggregate_reports_complete") is not True:
        raise ValueError("public aggregate reports are not recorded as complete")
    payload = {
        "schema_version": 1,
        "protocol_version": "2.0.0",
        "status": "frozen",
        "approved_by": "project_owner",
        "approved_at": policy["approved_at"],
        "algorithm": "SHA-256",
        "files": {
            "policy": {
                "path": policy_source.as_posix(),
                "sha256": file_sha256(policy_source),
            },
            "protocol_document": {
                "path": document_source.as_posix(),
                "sha256": file_sha256(document_source),
            },
        },
        "note": (
            "Frozen after project-owner approval; training remains project-owner-only "
            "and final-test locks remain in force."
        ),
    }
    payload["sha256"] = _sealed_hash(payload)
    return payload


def _validate_protocol_lock(
    lock_path: Path | None,
    *,
    policy_path: Path,
    protocol_document: Path,
    policy: dict[str, Any],
) -> tuple[bool, list[str], dict[str, Any] | None]:
    if lock_path is None or not lock_path.is_file():
        return False, ["frozen Route B protocol lock is missing"], None
    try:
        lock = _read_json(lock_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return False, [f"invalid protocol lock: {exc}"], None
    errors: list[str] = []
    if lock.get("sha256") != _sealed_hash(lock):
        errors.append("protocol lock self-hash mismatch")
    if lock.get("protocol_version") != "2.0.0" or lock.get("status") != "frozen":
        errors.append("protocol lock is not frozen version 2.0.0")
    if lock.get("approved_by") != "project_owner" or not _has_timezone(
        lock.get("approved_at")
    ):
        errors.append("protocol lock lacks project-owner approval with timezone")
    if lock.get("approved_at") != policy.get("approved_at"):
        errors.append("protocol lock approval timestamp differs from policy")
    locked_files = lock.get("files", {})
    for key, source in (("policy", policy_path), ("protocol_document", protocol_document)):
        locked = locked_files.get(key, {})
        if not isinstance(locked, dict) or locked.get("sha256") != file_sha256(source):
            errors.append(f"protocol lock file hash mismatch: {key}")
    return not errors, errors, lock


def _manifest_gates(
    manifest_path: Path,
) -> tuple[dict[str, bool], list[str], dict[str, Any]]:
    errors = validate_formal_mock_manifest(manifest_path)
    manifest = _read_json(manifest_path)
    splits = manifest.get("splits", {})
    risk_support = set(splits) == set(CONSTRUCTION_ROLES) and all(
        set(splits[role].get("risk_labels", {})) == set(RISK_LABELS)
        and all(value > 0 for value in splits[role]["risk_labels"].values())
        for role in CONSTRUCTION_ROLES
    )
    alignment_support = set(splits) == set(CONSTRUCTION_ROLES) and all(
        set(splits[role].get("task_alignment_labels", {}))
        == set(TASK_ALIGNMENT_LABELS)
        and all(value > 0 for value in splits[role]["task_alignment_labels"].values())
        for role in CONSTRUCTION_ROLES
    )
    traces = manifest.get("traces", {})
    split_rows = sum(int(item.get("rows", 0)) for item in splits.values())
    action_gate = (
        traces.get("executed") is False
        and traces.get("external_side_effects") is False
        and traces.get("rows") == split_rows
    )
    gates = {
        "candidate_manifest_replayed": not errors,
        "five_class_risk_support_gate_passed": risk_support,
        "four_class_alignment_support_gate_passed": alignment_support,
        "action_provenance_and_mock_trace_gate_passed": action_gate,
    }
    return gates, errors, manifest


def _integrity_gate(
    integrity_path: Path,
    *,
    policy_path: Path,
    policy: dict[str, Any],
    manifest: dict[str, Any],
) -> tuple[bool, list[str]]:
    try:
        report = _read_json(integrity_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return False, [f"invalid integrity report: {exc}"]
    errors = [str(item) for item in report.get("errors", [])]
    summary = report.get("summary", {})
    expected_threshold = policy.get("split_isolation", {}).get(
        "near_duplicate_threshold"
    )
    if report.get("near_duplicate_check_performed") is not True:
        errors.append("near-duplicate check was not performed")
    if report.get("near_threshold") != expected_threshold:
        errors.append("near-duplicate threshold differs from frozen policy")
    manifest_splits = manifest.get("splits", {})
    if summary.get("by_split") != {
        role: manifest_splits[role]["rows"] for role in sorted(manifest_splits)
    }:
        errors.append("integrity report split counts differ from candidate manifest")
    if summary.get("risk_alignment_mutual_information_bits") != 0.0:
        errors.append("Risk/Alignment construction is not independent at zero-bit target")
    near_summary = summary.get("template_representative_near_integrity", {})
    if near_summary.get("representatives", 0) <= 0:
        errors.append("template-representative near-duplicate evidence is missing")
    evidence = report.get("evidence", {})
    expected_hashes = {
        item.get("sha256") for item in manifest.get("splits", {}).values()
    }
    observed_hashes = {
        item.get("sha256") for item in evidence.get("inputs", [])
    }
    if observed_hashes != expected_hashes:
        errors.append("integrity report inputs do not exactly match candidate split hashes")
    config_evidence = evidence.get("config", {})
    if config_evidence.get("sha256") != file_sha256(policy_path):
        errors.append("integrity report policy hash cannot be replayed")
    source_routing = policy.get("source_routing", {})
    expected_locked_roles = {
        "injecagent": ["test_b"],
        "notinject": ["test_c"],
        "agentdojo_v0_1_35": ["test_d"],
    }
    if policy.get("split_isolation", {}).get("frozen_tests_used_for_design") is not False:
        errors.append("frozen tests were used for Route B design")
    for source, roles in expected_locked_roles.items():
        if source_routing.get(source, {}).get("roles") != roles:
            errors.append(f"locked evaluation routing drifted: {source}")
    return not errors, errors


def _audit_manifest_matches_candidate(
    audit_manifest: dict[str, Any], candidate_manifest: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    candidate_hashes = {
        evidence["sha256"] for evidence in candidate_manifest.get("splits", {}).values()
    }
    audit_inputs = audit_manifest.get("inputs", [])
    audit_hashes = {item.get("sha256") for item in audit_inputs}
    if audit_hashes != candidate_hashes:
        errors.append("audit inputs do not exactly match candidate split hashes")
    if audit_manifest.get("risk_rows") != 400:
        errors.append("Risk audit does not contain the preregistered 400 rows")
    if audit_manifest.get("alignment_rows") != 400:
        errors.append("Alignment audit does not contain the preregistered 400 rows")
    return errors


def _audit_gates(
    audit_analysis_path: Path | None,
    audit_manifest_path: Path | None,
    *,
    policy: dict[str, Any],
    candidate_manifest: dict[str, Any],
) -> tuple[dict[str, bool], list[str], dict[str, Any] | None]:
    gates = {
        "independent_human_audit_quality_gates_passed": False,
        "audit_adjudication_complete": False,
    }
    if audit_analysis_path is None or not audit_analysis_path.is_file():
        return gates, ["blind-audit analysis is missing"], None
    if audit_manifest_path is None or not audit_manifest_path.is_file():
        return gates, ["blind-audit manifest is missing"], None
    try:
        analysis = _read_json(audit_analysis_path)
        audit_manifest = _read_json(audit_manifest_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return gates, [f"invalid audit evidence: {exc}"], None
    errors = _audit_manifest_matches_candidate(audit_manifest, candidate_manifest)
    if analysis.get("review_mode") != "independent_human_blind":
        errors.append("audit analysis is not an independent human blind review")
    received = analysis.get("received_files", {})
    required_received = {
        "reviewer_a_risk",
        "reviewer_b_risk",
        "reviewer_a_alignment",
        "reviewer_b_alignment",
    }
    if set(received) != required_received:
        errors.append("audit analysis does not bind all four reviewer sheets")
    else:
        sealed_relative = audit_manifest.get("sealed_seed_labels", {}).get("path", "")
        sealed_path = audit_manifest_path.parent / str(sealed_relative)
        try:
            replay = analyze_blind_audits(
                reviewer_a_risk=received["reviewer_a_risk"]["path"],
                reviewer_b_risk=received["reviewer_b_risk"]["path"],
                reviewer_a_alignment=received["reviewer_a_alignment"]["path"],
                reviewer_b_alignment=received["reviewer_b_alignment"]["path"],
                sealed_seed_labels=sealed_path,
                audit_manifest=audit_manifest_path,
                policy=policy,
            )
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            errors.append(f"audit analysis replay failed: {exc}")
        else:
            if replay != analysis:
                errors.append("audit analysis does not match deterministic replay")
    gates["independent_human_audit_quality_gates_passed"] = (
        not errors
        and analysis.get("status") in READY_AUDIT_STATUSES
        and analysis.get("quality_gates_passed") is True
    )
    gates["audit_adjudication_complete"] = (
        gates["independent_human_audit_quality_gates_passed"]
        and analysis.get("adjudication_required") is False
    )
    if analysis.get("adjudication_required") is True:
        errors.append("reviewer disagreements require preserved, independent adjudication")
    return gates, errors, analysis


def evaluate_route_b_readiness(
    *,
    policy_path: str | Path,
    protocol_document: str | Path,
    protocol_lock: str | Path | None,
    candidate_manifest: str | Path,
    integrity_report: str | Path,
    audit_analysis: str | Path | None,
    audit_manifest: str | Path | None,
    public_report: str | Path,
) -> dict[str, Any]:
    policy_source = Path(policy_path)
    protocol_source = Path(protocol_document)
    manifest_source = Path(candidate_manifest)
    integrity_source = Path(integrity_report)
    public_source = Path(public_report)
    policy = load_route_b_policy(policy_source)
    gates, manifest_errors, manifest = _manifest_gates(manifest_source)
    integrity_passed, integrity_errors = _integrity_gate(
        integrity_source,
        policy_path=policy_source,
        policy=policy,
        manifest=manifest,
    )
    gates["split_and_test_lock_integrity_passed"] = integrity_passed
    audit_gates, audit_errors, analysis = _audit_gates(
        Path(audit_analysis) if audit_analysis is not None else None,
        Path(audit_manifest) if audit_manifest is not None else None,
        policy=policy,
        candidate_manifest=manifest,
    )
    gates.update(audit_gates)
    protocol_frozen = (
        policy.get("protocol_version") == "2.0.0"
        and policy.get("status") == "frozen"
        and policy.get("approved_by") == "project_owner"
        and _has_timezone(policy.get("approved_at"))
    )
    lock_passed, lock_errors, _ = _validate_protocol_lock(
        Path(protocol_lock) if protocol_lock is not None else None,
        policy_path=policy_source,
        protocol_document=protocol_source,
        policy=policy,
    )
    gates["protocol_2_0_0_approved_and_frozen"] = protocol_frozen and lock_passed
    gates["sample_size_precision_power_target_frozen"] = (
        policy.get("sample_size", {}).get("status") == "frozen"
    )
    gates["all_source_terms_and_attribution_approved"] = (
        policy.get("project_owned_mock_corpus_authorized") is True
        and policy.get("unapproved_cc_by_sa_and_noncommercial_sources_excluded") is True
        and manifest.get("source") == "IntentFenceProjectMock"
    )
    gates["v2_manifest_and_public_aggregate_reports_complete"] = (
        public_source.is_file()
        and public_source.stat().st_size > 0
        and policy.get("readiness", {}).get("public_aggregate_reports_complete") is True
    )
    gates["project_owner_formal_training_authorization_recorded"] = (
        policy.get("readiness", {}).get("formal_training_authorized") is True
    )
    blockers = [name for name, passed in gates.items() if not passed]
    validation_errors = manifest_errors + integrity_errors + audit_errors + lock_errors
    evidence: dict[str, Any] = {
        "policy": {"path": str(policy_source.resolve()), "sha256": file_sha256(policy_source)},
        "protocol_document": {
            "path": str(protocol_source.resolve()),
            "sha256": file_sha256(protocol_source),
        },
        "candidate_manifest": {
            "path": str(manifest_source.resolve()),
            "sha256": file_sha256(manifest_source),
            "sealed_sha256": manifest.get("sha256"),
        },
        "integrity_report": {
            "path": str(integrity_source.resolve()),
            "sha256": file_sha256(integrity_source),
        },
        "public_report": {
            "path": str(public_source.resolve()),
            "sha256": file_sha256(public_source) if public_source.is_file() else None,
        },
    }
    if protocol_lock is not None and Path(protocol_lock).is_file():
        evidence["protocol_lock"] = {
            "path": str(Path(protocol_lock).resolve()),
            "sha256": file_sha256(protocol_lock),
        }
    if audit_analysis is not None and Path(audit_analysis).is_file():
        evidence["audit_analysis"] = {
            "path": str(Path(audit_analysis).resolve()),
            "sha256": file_sha256(audit_analysis),
            "status": analysis.get("status") if analysis else None,
        }
    authorized = all(gates.values()) and not validation_errors
    return {
        "schema_version": 1,
        "protocol_version": policy.get("protocol_version"),
        "data_version": manifest.get("data_version"),
        "status": "ready_for_project_owner_training" if authorized else "readiness_blocked",
        "formal_training_authorized": authorized,
        "training_executor": "project_owner_only",
        "final_test_lock_remains_active": True,
        "gates": gates,
        "readiness_blockers": blockers,
        "validation_errors": validation_errors,
        "evidence": evidence,
    }
