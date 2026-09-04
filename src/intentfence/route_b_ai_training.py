from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from intentfence.constants import RISK_LABELS, TASK_ALIGNMENT_LABELS
from intentfence.data import file_sha256
from intentfence.route_b import load_route_b_policy
from intentfence.route_b_ai_review import analyze_dual_ai_reviews
from intentfence.route_b_readiness import (
    _integrity_gate,
    _manifest_gates,
    _public_report_gate,
)

AI_TRAINING_PROTOCOL_VERSION = "2.2.0-ai-assisted-engineering.1"
AI_TRAINING_AUTHORIZATION_MODE = "ai_reviewed_engineering"
AI_TRAINING_EVIDENCE_CLASS = "ai_reviewed_engineering_only"
AI_REVIEW_MODE = "dual_ai_engineering"
AI_REVIEW_SLOTS = ("ai_a", "ai_b")
CONSTRUCTION_ROLES = ("train", "validation", "calibration", "test_a")
EXPECTED_AI_GATE_VALUES = {
    "completed_fraction_minimum": 0.95,
    "raw_interreviewer_agreement_minimum": 0.90,
    "cohen_kappa_minimum": 0.80,
    "per_seed_class_agreement_minimum": 0.90,
    "action_realism_realistic_fraction_minimum": 0.95,
}


def _read_json(path: Path, *, description: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{description} is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{description} must be a JSON object")
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
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _same_path(left: str | Path, right: str | Path) -> bool:
    left_resolved = os.path.normcase(str(Path(left).resolve()))
    right_resolved = os.path.normcase(str(Path(right).resolve()))
    if left_resolved == right_resolved:
        return True

    # Evidence packages may be generated on Windows and replayed from a
    # relocated checkout on Linux. Compare the path suffix below the project
    # directory after the explicit file hash check has bound the real file.
    project_name = Path.cwd().resolve().name.casefold()

    def relative_tail(value: str | Path) -> tuple[str, ...]:
        parts = tuple(
            part.casefold()
            for part in str(value).replace("\\", "/").split("/")
            if part not in {"", "."}
        )
        for index, part in enumerate(parts):
            if part == project_name:
                return parts[index + 1 :]
        return parts

    return relative_tail(left) == relative_tail(right)


def _file_binding(path: Path) -> dict[str, str]:
    resolved = path.resolve()
    try:
        portable_path = resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        portable_path = str(resolved)
    return {"path": portable_path, "sha256": file_sha256(path)}


def _readiness_comparison_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Make readiness replay comparable after moving a project to another host.

    Evidence paths are descriptive and may contain host-specific absolute prefixes.
    The validator binds the actual files through its explicit path arguments and
    compares their SHA-256 values, so only the display path is normalized here.
    """
    comparable = deepcopy(payload)
    evidence = comparable.get("evidence")
    if isinstance(evidence, dict):
        for binding in evidence.values():
            if isinstance(binding, dict) and isinstance(binding.get("path"), str):
                binding["path"] = "<relocated-evidence-path>"
    return comparable


def _ai_review_comparison_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Make AI-review replay comparable after moving a project to another host."""
    comparable = deepcopy(payload)
    for name in ("ai_review_manifest", "audit_manifest"):
        binding = comparable.get(name)
        if isinstance(binding, dict) and isinstance(binding.get("path"), str):
            binding["path"] = "<relocated-ai-review-evidence-path>"
    return comparable


def _lock_file_binding(path: Path) -> dict[str, str]:
    resolved = path.resolve()
    try:
        lock_path = resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        lock_path = str(resolved)
    return {"path": lock_path, "sha256": file_sha256(path)}


def _configured_path(
    policy: dict[str, Any],
    *,
    key: str,
    explicit: str | Path | None,
) -> Path:
    if explicit is not None:
        return Path(explicit)
    value = policy.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"AI training policy is missing {key}")
    return Path(value)


def _validate_ai_training_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != 1:
        errors.append("AI training policy schema_version must be 1")
    if policy.get("protocol_version") != AI_TRAINING_PROTOCOL_VERSION:
        errors.append("AI training policy protocol_version drifted")
    if policy.get("status") != "frozen":
        errors.append("AI training policy must be frozen")
    if policy.get("selected_route") != "B-ai-assisted-engineering":
        errors.append("AI training policy selected_route is not B-ai-assisted-engineering")
    if policy.get("selected_by") != "project_owner":
        errors.append("AI training policy requires project-owner route selection")
    if policy.get("approved_by") != "project_owner" or not _has_timezone(
        policy.get("approved_at")
    ):
        errors.append("AI training policy requires project-owner approval with timezone")
    if policy.get("evidence_status") != AI_TRAINING_EVIDENCE_CLASS:
        errors.append("AI training policy evidence_status must be ai_reviewed_engineering_only")
    if policy.get("project_owned_mock_corpus_authorized") is not True:
        errors.append("AI training route requires the project-owned mock corpus authorization")
    if policy.get("unapproved_cc_by_sa_and_noncommercial_sources_excluded") is not True:
        errors.append("AI training route must exclude unapproved external sources")
    if tuple(policy.get("risk_labels", ())) != RISK_LABELS:
        errors.append("AI training policy Risk labels differ from the canonical five labels")
    if tuple(policy.get("task_alignment_labels", ())) != TASK_ALIGNMENT_LABELS:
        errors.append(
            "AI training policy Alignment labels differ from the canonical four labels"
        )

    audit = policy.get("audit", {})
    if audit.get("review_mode") != AI_REVIEW_MODE:
        errors.append("AI training policy audit review_mode must be dual_ai_engineering")
    if audit.get("codex_executed_audit_default") != "exactly_two_independent_ai_reviewers":
        errors.append("AI training policy must require exactly two AI reviewers")
    if audit.get("independent_human_reviewers_required") != 0:
        errors.append("AI training policy must not require a human reviewer for this route")
    if audit.get("independent_ai_reviewers_required") != 2:
        errors.append("AI training policy must require two AI reviewers")
    if audit.get("ai_review_counts_as_independent_human_review") is not False:
        errors.append("AI review must not count as independent human review")
    if audit.get("distinct_provider_model_revision_required") is not True:
        errors.append("AI reviewer identities must be distinct and versioned")
    if audit.get("temperature_must_equal") != 0:
        errors.append("AI reviewer temperature must be fixed at zero")
    if audit.get("seed_labels_hidden") is not True:
        errors.append("AI training policy must keep seed labels hidden")
    if audit.get("reviewer_outputs_hidden_from_each_other") is not True:
        errors.append("AI training policy must keep reviewer outputs blind")
    if audit.get("raw_outputs_preserved") is not True:
        errors.append("AI training policy must preserve raw reviewer outputs")
    sample_rows = audit.get("sample_rows", {})
    if not all(isinstance(sample_rows.get(task), int) and sample_rows[task] > 0 for task in ("risk", "alignment")):
        errors.append("AI training policy must define positive Risk and Alignment sample sizes")
    gates = audit.get("preregistered_quality_gates", {})
    for key, expected in EXPECTED_AI_GATE_VALUES.items():
        if gates.get(key) != expected:
            errors.append(f"AI quality-gate threshold drifted: {key}")
    if (
        gates.get("failed_gate_action")
        != "preserve_failure_require_owner_risk_acceptance_for_engineering_only"
    ):
        errors.append("AI quality-gate failure action is not fail-closed")

    ai_training = policy.get("ai_training", {})
    if ai_training.get("enabled") is not True:
        errors.append("AI engineering training route is not enabled")
    if ai_training.get("scope") != "engineering_only":
        errors.append("AI training scope must remain engineering_only")
    if ai_training.get("owner_must_execute") is not True:
        errors.append("AI engineering training must remain project-owner executed")
    if ai_training.get("owner_risk_acceptance_required") is not True:
        errors.append("AI training route must require project-owner risk acceptance")

    final_test = policy.get("final_test", {})
    calibration = policy.get("calibration", {})
    if final_test.get("locked") is not True:
        errors.append("AI training route must keep the final-test lock active")
    if calibration.get("locked") is not True:
        errors.append("AI training route must keep the calibration lock active")
    readiness = policy.get("readiness", {})
    if readiness.get("human_verified") is not False:
        errors.append("AI training route must keep human_verified=false")
    if readiness.get("formal_training_authorized") is not False:
        errors.append("AI training route must keep formal_training_authorized=false")
    if readiness.get("engineering_training_authorized") is not False:
        errors.append("AI training route must not pre-authorize engineering training")

    accepted_versions = policy.get("accepted_ai_review_protocol_versions", [])
    if not isinstance(accepted_versions, list) or not accepted_versions:
        errors.append("AI training policy must list accepted AI review protocol versions")
    return errors


def build_ai_training_protocol_lock(
    *,
    policy_path: str | Path,
    protocol_document: str | Path,
    integrity_policy_path: str | Path | None = None,
    ai_review_policy_path: str | Path | None = None,
) -> dict[str, Any]:
    policy_source = Path(policy_path)
    document_source = Path(protocol_document)
    policy = load_route_b_policy(policy_source)
    errors = _validate_ai_training_policy(policy)
    integrity_source = _configured_path(
        policy,
        key="integrity_source_policy_path",
        explicit=integrity_policy_path,
    )
    ai_review_source = _configured_path(
        policy,
        key="ai_review_policy_path",
        explicit=ai_review_policy_path,
    )
    for source, description in (
        (policy_source, "AI training policy"),
        (document_source, "AI training protocol document"),
        (integrity_source, "integrity source policy"),
        (ai_review_source, "AI review policy"),
    ):
        if not source.is_file():
            errors.append(f"{description} is missing: {source}")
    if errors:
        raise ValueError("; ".join(errors))

    payload = {
        "schema_version": 1,
        "protocol_version": AI_TRAINING_PROTOCOL_VERSION,
        "status": "frozen",
        "training_route": "B-ai-assisted-engineering",
        "training_scope": "engineering_only",
        "approved_by": "project_owner",
        "approved_at": policy["approved_at"],
        "algorithm": "SHA-256",
        "evidence_status": AI_TRAINING_EVIDENCE_CLASS,
        "human_verified": False,
        "formal_training_authorized": False,
        "engineering_training_authorized": False,
        "final_test_lock_remains_active": True,
        "calibration_lock_remains_active": True,
        "files": {
            "policy": _lock_file_binding(policy_source),
            "protocol_document": _lock_file_binding(document_source),
            "integrity_source_policy": _lock_file_binding(integrity_source),
            "ai_review_policy": _lock_file_binding(ai_review_source),
        },
        "note": (
            "Frozen owner-approved amendment: two distinct AI reviewers may provide "
            "explicitly labeled engineering evidence. This does not claim human verification, "
            "does not authorize formal training, and does not unlock calibration or final tests."
        ),
    }
    payload["sha256"] = _sealed_hash(payload)
    return payload


def _protocol_lock_gate(
    lock_path: Path | None,
    *,
    policy_path: Path,
    protocol_document: Path,
    integrity_policy_path: Path,
    ai_review_policy_path: Path,
    policy: dict[str, Any],
) -> tuple[bool, list[str]]:
    if lock_path is None or not lock_path.is_file():
        return False, ["frozen AI training protocol lock is missing"]
    try:
        lock = _read_json(lock_path, description="AI training protocol lock")
    except ValueError as exc:
        return False, [str(exc)]
    errors: list[str] = []
    if lock.get("sha256") != _sealed_hash(lock):
        errors.append("AI training protocol lock self-hash mismatch")
    if lock.get("schema_version") != 1:
        errors.append("AI training protocol lock schema_version must be 1")
    if lock.get("algorithm") != "SHA-256":
        errors.append("AI training protocol lock algorithm must be SHA-256")
    if lock.get("protocol_version") != AI_TRAINING_PROTOCOL_VERSION:
        errors.append("AI training protocol lock version drifted")
    if lock.get("status") != "frozen":
        errors.append("AI training protocol lock is not frozen")
    if lock.get("training_route") != "B-ai-assisted-engineering":
        errors.append("AI training protocol lock route drifted")
    if lock.get("training_scope") != "engineering_only":
        errors.append("AI training protocol lock scope drifted")
    if lock.get("approved_by") != "project_owner" or not _has_timezone(
        lock.get("approved_at")
    ):
        errors.append("AI training protocol lock lacks project-owner approval with timezone")
    if lock.get("approved_at") != policy.get("approved_at"):
        errors.append("AI training protocol lock approval timestamp differs from policy")
    for field, expected in (
        ("evidence_status", AI_TRAINING_EVIDENCE_CLASS),
        ("human_verified", False),
        ("formal_training_authorized", False),
        ("engineering_training_authorized", False),
        ("final_test_lock_remains_active", True),
        ("calibration_lock_remains_active", True),
    ):
        if lock.get(field) != expected:
            errors.append(f"AI training protocol lock {field} is not {expected!r}")
    locked_files = lock.get("files", {})
    for key, source in (
        ("policy", policy_path),
        ("protocol_document", protocol_document),
        ("integrity_source_policy", integrity_policy_path),
        ("ai_review_policy", ai_review_policy_path),
    ):
        entry = locked_files.get(key, {})
        if (
            not isinstance(entry, dict)
            or not _same_path(entry.get("path", ""), source)
            or entry.get("sha256") != file_sha256(source)
        ):
            errors.append(f"AI training protocol lock file hash mismatch: {key}")
    return not errors, errors


def validate_ai_training_protocol_lock(
    *,
    lock_path: str | Path,
    policy_path: str | Path,
    protocol_document: str | Path,
    integrity_policy_path: str | Path | None = None,
    ai_review_policy_path: str | Path | None = None,
) -> dict[str, Any]:
    policy_source = Path(policy_path)
    policy = load_route_b_policy(policy_source)
    integrity_source = _configured_path(
        policy,
        key="integrity_source_policy_path",
        explicit=integrity_policy_path,
    )
    ai_review_source = _configured_path(
        policy,
        key="ai_review_policy_path",
        explicit=ai_review_policy_path,
    )
    errors = _validate_ai_training_policy(policy)
    passed, lock_errors = _protocol_lock_gate(
        Path(lock_path),
        policy_path=policy_source,
        protocol_document=Path(protocol_document),
        integrity_policy_path=integrity_source,
        ai_review_policy_path=ai_review_source,
        policy=policy,
    )
    errors.extend(lock_errors)
    if errors:
        raise ValueError("; ".join(errors))
    return {
        "status": "ai_training_protocol_lock_validated",
        "protocol_version": AI_TRAINING_PROTOCOL_VERSION,
        "lock_sha256": file_sha256(lock_path),
        "policy_sha256": file_sha256(policy_source),
        "passed": passed,
    }


def _resolve_ai_review_output_path(metadata_path: Path, value: Any) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else metadata_path.parent / path


def _candidate_audit_binding(
    audit_manifest: dict[str, Any],
    *,
    candidate_manifest: dict[str, Any],
    expected_rows: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    if audit_manifest.get("review_mode") != AI_REVIEW_MODE:
        errors.append("AI audit manifest review_mode must be dual_ai_engineering")
    if audit_manifest.get("risk_rows") != expected_rows.get("risk"):
        errors.append("AI audit Risk row count differs from the frozen AI route")
    if audit_manifest.get("alignment_rows") != expected_rows.get("alignment"):
        errors.append("AI audit Alignment row count differs from the frozen AI route")
    candidate_hashes = {
        item.get("sha256")
        for item in candidate_manifest.get("splits", {}).values()
        if isinstance(item, dict)
    }
    audit_hashes = {
        item.get("sha256")
        for item in audit_manifest.get("inputs", [])
        if isinstance(item, dict)
    }
    if audit_hashes != candidate_hashes:
        errors.append("AI audit inputs do not exactly match candidate split hashes")
    return errors


def _ai_review_evidence_gate(
    *,
    analysis_path: Path,
    ai_review_manifest_path: Path,
    audit_manifest_path: Path,
    candidate_manifest: dict[str, Any],
    policy: dict[str, Any],
    ai_review_policy_path: Path,
) -> tuple[bool, list[str], dict[str, Any], dict[str, Any]]:
    try:
        analysis = _read_json(analysis_path, description="AI review analysis")
        ai_manifest = _read_json(
            ai_review_manifest_path, description="AI review manifest"
        )
        audit_manifest = _read_json(audit_manifest_path, description="AI audit manifest")
        ai_review_policy = load_route_b_policy(ai_review_policy_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return False, [f"invalid AI review evidence: {exc}"], {}, {}

    errors: list[str] = []
    accepted_versions = policy.get("accepted_ai_review_protocol_versions", [])
    if ai_manifest.get("protocol_version") not in accepted_versions:
        errors.append("AI review manifest protocol_version is not accepted by the AI training route")
    if analysis.get("review_mode") != AI_REVIEW_MODE:
        errors.append("AI review analysis review_mode must be dual_ai_engineering")
    if analysis.get("evidence_status") != AI_TRAINING_EVIDENCE_CLASS:
        errors.append("AI review analysis evidence_status is not engineering-only")
    if analysis.get("status") not in {
        "ai_quality_gates_passed_engineering_only",
        "ai_quality_gates_failed_engineering_only",
    }:
        errors.append("AI review analysis has no accepted engineering-only status")
    if analysis.get("validation_errors") != []:
        errors.append("AI review analysis contains validation errors")
    if analysis.get("human_verified") is not False:
        errors.append("AI review analysis must keep human_verified=false")
    if analysis.get("formal_training_authorized") is not False:
        errors.append("AI review analysis must keep formal_training_authorized=false")
    manifest_binding = analysis.get("ai_review_manifest", {})
    if not isinstance(manifest_binding, dict) or not _same_path(
        manifest_binding.get("path", ""), ai_review_manifest_path
    ):
        errors.append("AI review analysis does not bind the submitted AI review manifest path")
    elif manifest_binding.get("sha256") != file_sha256(ai_review_manifest_path):
        errors.append("AI review analysis AI manifest hash does not match")
    audit_binding = analysis.get("audit_manifest", {})
    if not isinstance(audit_binding, dict) or not _same_path(
        audit_binding.get("path", ""), audit_manifest_path
    ):
        errors.append("AI review analysis does not bind the submitted audit manifest path")
    elif audit_binding.get("sha256") != file_sha256(audit_manifest_path):
        errors.append("AI review analysis audit manifest hash does not match")
    errors.extend(
        _candidate_audit_binding(
            audit_manifest,
            candidate_manifest=candidate_manifest,
            expected_rows=policy.get("audit", {}).get("sample_rows", {}),
        )
    )
    reviewers = ai_manifest.get("reviewers")
    if not isinstance(reviewers, dict) or set(reviewers) != set(AI_REVIEW_SLOTS):
        errors.append("AI review manifest must contain exactly ai_a and ai_b")
        reviewers = {}
    if len(reviewers) == 2:
        identities = [
            tuple(
                str(reviewers[slot].get(key, "")).strip()
                for key in ("provider", "model", "revision")
            )
            for slot in AI_REVIEW_SLOTS
            if isinstance(reviewers[slot], dict)
        ]
        if len(identities) != 2 or identities[0] == identities[1]:
            errors.append("AI reviewer provider/model/revision identities must be distinct")

    received = {
        "ai_a_risk": None,
        "ai_b_risk": None,
        "ai_a_alignment": None,
        "ai_b_alignment": None,
    }
    if len(reviewers) == 2:
        for slot in AI_REVIEW_SLOTS:
            raw_files = reviewers.get(slot, {}).get("raw_output_files", {})
            received[f"{slot}_risk"] = _resolve_ai_review_output_path(
                ai_review_manifest_path, raw_files.get("risk_path", "")
            )
            received[f"{slot}_alignment"] = _resolve_ai_review_output_path(
                ai_review_manifest_path, raw_files.get("alignment_path", "")
            )
    sealed_relative = audit_manifest.get("sealed_seed_labels", {}).get("path", "")
    sealed_seed_labels = audit_manifest_path.parent / str(sealed_relative)
    if not sealed_seed_labels.is_file():
        errors.append(f"sealed AI audit seed labels are missing: {sealed_seed_labels}")

    if not errors:
        try:
            replayed = analyze_dual_ai_reviews(
                reviewer_a_risk=received["ai_a_risk"],
                reviewer_b_risk=received["ai_b_risk"],
                reviewer_a_alignment=received["ai_a_alignment"],
                reviewer_b_alignment=received["ai_b_alignment"],
                sealed_seed_labels=sealed_seed_labels,
                audit_manifest=audit_manifest_path,
                ai_review_manifest=ai_review_manifest_path,
                policy=ai_review_policy,
            )
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            errors.append(f"AI review analysis replay failed: {exc}")
        else:
            if _ai_review_comparison_payload(replayed) != _ai_review_comparison_payload(
                analysis
            ):
                errors.append("AI review analysis does not match deterministic replay")

    return not errors, errors, analysis, ai_manifest


def _validate_candidate_and_training_inputs(
    candidate_manifest: dict[str, Any],
    *,
    expected_candidate: str,
    candidate_manifest_path: Path,
    train_path: Path,
    validation_path: Path,
) -> list[str]:
    errors: list[str] = []
    if candidate_manifest.get("data_version") != expected_candidate:
        errors.append("candidate manifest data_version does not match the expected candidate")
    if candidate_manifest.get("sha256") != _sealed_hash(candidate_manifest):
        errors.append("candidate manifest self-hash mismatch")
    if candidate_manifest.get("formal_training_authorized") is not False:
        errors.append("candidate manifest must keep formal_training_authorized=false")
    splits = candidate_manifest.get("splits")
    if not isinstance(splits, dict) or set(splits) != set(CONSTRUCTION_ROLES):
        errors.append("candidate manifest must contain exactly train/validation/calibration/test_a")
        return errors
    for role, observed_path in (("train", train_path), ("validation", validation_path)):
        entry = splits.get(role)
        if not isinstance(entry, dict):
            errors.append(f"candidate manifest split is missing: {role}")
            continue
        expected_path = candidate_manifest_path.parent / str(entry.get("path", ""))
        if not _same_path(observed_path, expected_path):
            errors.append(f"training {role} path does not match candidate manifest")
        if entry.get("sha256") != file_sha256(observed_path):
            errors.append(f"training {role} split hash does not match candidate manifest")
    return errors


def build_ai_training_readiness(
    *,
    policy_path: str | Path,
    protocol_document: str | Path,
    protocol_lock: str | Path | None,
    candidate_manifest: str | Path,
    integrity_report: str | Path,
    ai_review_analysis: str | Path,
    ai_review_manifest: str | Path,
    audit_manifest: str | Path,
    public_report: str | Path,
    integrity_policy_path: str | Path | None = None,
    ai_review_policy_path: str | Path | None = None,
) -> dict[str, Any]:
    policy_source = Path(policy_path)
    protocol_source = Path(protocol_document)
    lock_source = Path(protocol_lock) if protocol_lock is not None else None
    manifest_source = Path(candidate_manifest)
    integrity_source = Path(integrity_report)
    analysis_source = Path(ai_review_analysis)
    ai_manifest_source = Path(ai_review_manifest)
    audit_manifest_source = Path(audit_manifest)
    public_source = Path(public_report)
    policy = load_route_b_policy(policy_source)
    integrity_policy_source = _configured_path(
        policy,
        key="integrity_source_policy_path",
        explicit=integrity_policy_path,
    )
    ai_review_policy_source = _configured_path(
        policy,
        key="ai_review_policy_path",
        explicit=ai_review_policy_path,
    )
    paths = {
        "policy": policy_source,
        "protocol_document": protocol_source,
        "integrity_policy": integrity_policy_source,
        "ai_review_policy": ai_review_policy_source,
        "protocol_lock": lock_source,
        "candidate_manifest": manifest_source,
        "integrity_report": integrity_source,
        "ai_review_analysis": analysis_source,
        "ai_review_manifest": ai_manifest_source,
        "audit_manifest": audit_manifest_source,
        "public_report": public_source,
    }
    missing = [
        f"{name} is missing: {path}"
        for name, path in paths.items()
        if path is None or not path.is_file()
    ]
    if missing:
        raise ValueError("; ".join(missing))

    policy_errors = _validate_ai_training_policy(policy)
    try:
        manifest_gates, manifest_errors, manifest = _manifest_gates(manifest_source)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        manifest_gates = {
            "candidate_manifest_replayed": False,
            "five_class_risk_support_gate_passed": False,
            "four_class_alignment_support_gate_passed": False,
            "action_provenance_and_mock_trace_gate_passed": False,
        }
        manifest_errors = [f"candidate manifest replay failed: {exc}"]
        manifest = {}

    try:
        integrity_policy = load_route_b_policy(integrity_policy_source)
        integrity_passed, integrity_errors = _integrity_gate(
            integrity_source,
            policy_path=integrity_policy_source,
            policy=integrity_policy,
            manifest=manifest,
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        integrity_passed, integrity_errors = False, [f"integrity replay failed: {exc}"]

    ai_passed, ai_errors, analysis, _ = _ai_review_evidence_gate(
        analysis_path=analysis_source,
        ai_review_manifest_path=ai_manifest_source,
        audit_manifest_path=audit_manifest_source,
        candidate_manifest=manifest,
        policy=policy,
        ai_review_policy_path=ai_review_policy_source,
    )
    lock_passed, lock_errors = _protocol_lock_gate(
        lock_source,
        policy_path=policy_source,
        protocol_document=protocol_source,
        integrity_policy_path=integrity_policy_source,
        ai_review_policy_path=ai_review_policy_source,
        policy=policy,
    )
    public_passed, public_errors = _public_report_gate(
        public_source,
        candidate_manifest=manifest,
    )
    gates = {
        **manifest_gates,
        "split_and_test_lock_integrity_passed": integrity_passed,
        "dual_ai_review_package_structurally_valid": ai_passed,
        "ai_training_protocol_frozen": not policy_errors and lock_passed,
        "public_aggregate_reports_complete": (
            public_passed
            and policy.get("readiness", {}).get("public_aggregate_reports_complete") is True
        ),
        "final_test_and_calibration_locks_active": (
            policy.get("final_test", {}).get("locked") is True
            and policy.get("calibration", {}).get("locked") is True
        ),
    }
    validation_errors = (
        policy_errors
        + manifest_errors
        + integrity_errors
        + ai_errors
        + lock_errors
        + public_errors
    )
    blockers = [name for name, passed in gates.items() if not passed]
    quality_passed = analysis.get("quality_gates_passed") is True
    structurally_ready = all(gates.values()) and not validation_errors
    evidence = {
        name: _file_binding(path)
        for name, path in paths.items()
        if path is not None
    }
    evidence["candidate_manifest"]["sealed_sha256"] = manifest.get("sha256")
    return {
        "schema_version": 1,
        "protocol_version": policy.get("protocol_version"),
        "data_version": manifest.get("data_version"),
        "status": (
            "eligible_for_owner_ai_engineering_authorization"
            if structurally_ready
            else "ai_engineering_readiness_blocked"
        ),
        "engineering_training_eligible": structurally_ready,
        "engineering_training_authorized": False,
        "formal_training_authorized": False,
        "training_executor": "project_owner_only",
        "training_evidence_class": AI_TRAINING_EVIDENCE_CLASS,
        "human_verified": False,
        "final_test_lock_remains_active": True,
        "calibration_lock_remains_active": True,
        "owner_risk_acceptance_required": True,
        "ai_quality_gate_status": analysis.get("status"),
        "ai_quality_gates_passed": quality_passed,
        "ai_quality_gate_failure_requires_owner_acceptance": (
            bool(analysis) and not quality_passed
        ),
        "ai_disagreement_count": sum(
            len(analysis.get("construct_agreement_metrics", {}).get(task, {}).get(
                "disagreement_audit_ids", []
            ))
            for task in ("risk", "alignment")
        ),
        "gates": gates,
        "readiness_blockers": blockers,
        "validation_errors": validation_errors,
        "evidence": evidence,
    }


def _validate_ai_authorization_fields(
    authorization: dict[str, Any],
    *,
    expected_candidate: str,
    candidate_manifest_path: Path,
    readiness_report_path: Path,
    protocol_lock_path: Path,
    integrity_policy_path: Path,
    ai_review_policy_path: Path,
    ai_review_analysis_path: Path,
    ai_review_manifest_path: Path,
    readiness: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    expected_values = {
        "schema_version": 1,
        "candidate_id": expected_candidate,
        "protocol_version": AI_TRAINING_PROTOCOL_VERSION,
        "training_authorization_mode": AI_TRAINING_AUTHORIZATION_MODE,
        "human_verified": False,
        "formal_training_authorized": False,
        "engineering_training_authorized": True,
        "training_executor": "project_owner_only",
        "ai_evidence_class": AI_TRAINING_EVIDENCE_CLASS,
        "final_test_lock_remains_active": True,
        "calibration_lock_remains_active": True,
    }
    for field, expected in expected_values.items():
        if authorization.get(field) != expected:
            errors.append(f"AI training authorization {field} must be {expected!r}")
    if not isinstance(authorization.get("approved_by_project_owner"), str) or not authorization[
        "approved_by_project_owner"
    ].strip():
        errors.append("AI training authorization requires approved_by_project_owner")
    if not _has_timezone(authorization.get("approved_at")):
        errors.append("AI training authorization approved_at must include a timezone")
    if not isinstance(authorization.get("ai_quality_gate_failure_accepted"), bool):
        errors.append("AI training authorization requires boolean ai_quality_gate_failure_accepted")
    if not readiness.get("ai_quality_gates_passed", False):
        if authorization.get("ai_quality_gate_failure_accepted") is not True:
            errors.append(
                "failed AI quality gates require ai_quality_gate_failure_accepted=true"
            )
        reason = authorization.get("ai_quality_gate_failure_reason")
        if not isinstance(reason, str) or not reason.strip():
            errors.append("failed AI quality gates require a non-empty acceptance reason")

    expected_hashes = {
        "candidate_manifest_sha256": candidate_manifest_path,
        "readiness_report_sha256": readiness_report_path,
        "protocol_lock_sha256": protocol_lock_path,
        "integrity_policy_sha256": integrity_policy_path,
        "ai_review_policy_sha256": ai_review_policy_path,
        "ai_review_analysis_sha256": ai_review_analysis_path,
        "ai_review_manifest_sha256": ai_review_manifest_path,
    }
    for field, path in expected_hashes.items():
        try:
            observed = file_sha256(path)
        except OSError as exc:
            errors.append(f"cannot hash AI authorization evidence {field}: {exc}")
            continue
        if authorization.get(field) != observed:
            errors.append(f"AI training authorization {field} does not match bound evidence")
    return errors


def validate_ai_training_authorization(
    *,
    authorization_path: str | Path,
    expected_candidate: str,
    candidate_manifest_path: str | Path,
    train_path: str | Path,
    validation_path: str | Path,
    readiness_report_path: str | Path,
    protocol_lock_path: str | Path,
    policy_path: str | Path,
    protocol_document_path: str | Path,
    integrity_report_path: str | Path,
    audit_analysis_path: str | Path,
    audit_manifest_path: str | Path,
    public_report_path: str | Path,
    ai_review_manifest_path: str | Path | None = None,
    integrity_policy_path: str | Path | None = None,
    ai_review_policy_path: str | Path | None = None,
) -> dict[str, Any]:
    paths = {
        "authorization": Path(authorization_path),
        "candidate_manifest": Path(candidate_manifest_path),
        "train": Path(train_path),
        "validation": Path(validation_path),
        "readiness_report": Path(readiness_report_path),
        "protocol_lock": Path(protocol_lock_path),
        "policy": Path(policy_path),
        "protocol_document": Path(protocol_document_path),
        "integrity_report": Path(integrity_report_path),
        "audit_analysis": Path(audit_analysis_path),
        "audit_manifest": Path(audit_manifest_path),
        "public_report": Path(public_report_path),
    }
    errors: list[str] = []
    for name, path in paths.items():
        if not path.is_file():
            errors.append(f"{name} is missing: {path}")
    if errors:
        raise ValueError("; ".join(errors))

    policy = load_route_b_policy(paths["policy"])
    integrity_policy_source = _configured_path(
        policy,
        key="integrity_source_policy_path",
        explicit=integrity_policy_path,
    )
    ai_review_policy_source = _configured_path(
        policy,
        key="ai_review_policy_path",
        explicit=ai_review_policy_path,
    )
    authorization = _read_json(paths["authorization"], description="AI training authorization")
    stored_analysis = _read_json(paths["audit_analysis"], description="AI review analysis")
    if ai_review_manifest_path is None:
        manifest_binding = stored_analysis.get("ai_review_manifest", {})
        ai_review_manifest_path = manifest_binding.get("path")
    if ai_review_manifest_path is None:
        raise ValueError("AI training authorization requires an AI review manifest path")
    ai_manifest_source = Path(ai_review_manifest_path)
    if not ai_manifest_source.is_file():
        raise ValueError(f"ai_review_manifest is missing: {ai_manifest_source}")
    all_bound_paths = {
        **paths,
        "integrity_policy": integrity_policy_source,
        "ai_review_policy": ai_review_policy_source,
        "ai_review_manifest": ai_manifest_source,
    }
    if paths["authorization"].resolve() in {
        path.resolve() for name, path in all_bound_paths.items() if name != "authorization"
    }:
        errors.append("AI training authorization must be separate from bound evidence")

    candidate_manifest = _read_json(
        paths["candidate_manifest"], description="candidate manifest"
    )
    errors.extend(
        _validate_candidate_and_training_inputs(
            candidate_manifest,
            expected_candidate=expected_candidate,
            candidate_manifest_path=paths["candidate_manifest"],
            train_path=paths["train"],
            validation_path=paths["validation"],
        )
    )
    readiness = _read_json(paths["readiness_report"], description="AI readiness report")
    errors.extend(
        _validate_ai_authorization_fields(
            authorization,
            expected_candidate=expected_candidate,
            candidate_manifest_path=paths["candidate_manifest"],
            readiness_report_path=paths["readiness_report"],
            protocol_lock_path=paths["protocol_lock"],
            integrity_policy_path=integrity_policy_source,
            ai_review_policy_path=ai_review_policy_source,
            ai_review_analysis_path=paths["audit_analysis"],
            ai_review_manifest_path=ai_manifest_source,
            readiness=readiness,
        )
    )
    if readiness.get("status") != "eligible_for_owner_ai_engineering_authorization":
        errors.append("AI readiness report is not eligible for owner AI engineering authorization")
    if readiness.get("engineering_training_eligible") is not True:
        errors.append("AI readiness report does not mark engineering_training_eligible=true")
    if readiness.get("engineering_training_authorized") is not False:
        errors.append("AI readiness report must keep engineering_training_authorized=false")
    if readiness.get("formal_training_authorized") is not False:
        errors.append("AI readiness report must keep formal_training_authorized=false")
    if readiness.get("human_verified") is not False:
        errors.append("AI readiness report must keep human_verified=false")
    if readiness.get("training_executor") != "project_owner_only":
        errors.append("AI readiness report training executor is not project_owner_only")
    if readiness.get("final_test_lock_remains_active") is not True:
        errors.append("AI readiness report must keep the final-test lock active")
    if readiness.get("calibration_lock_remains_active") is not True:
        errors.append("AI readiness report must keep the calibration lock active")
    if readiness.get("readiness_blockers") != []:
        errors.append("AI readiness report contains blockers")
    if readiness.get("validation_errors") != []:
        errors.append("AI readiness report contains validation errors")

    try:
        replayed = build_ai_training_readiness(
            policy_path=paths["policy"],
            protocol_document=paths["protocol_document"],
            protocol_lock=paths["protocol_lock"],
            candidate_manifest=paths["candidate_manifest"],
            integrity_report=paths["integrity_report"],
            ai_review_analysis=paths["audit_analysis"],
            ai_review_manifest=ai_manifest_source,
            audit_manifest=paths["audit_manifest"],
            public_report=paths["public_report"],
            integrity_policy_path=integrity_policy_source,
            ai_review_policy_path=ai_review_policy_source,
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        errors.append(f"AI readiness deterministic replay failed: {exc}")
    else:
        if _readiness_comparison_payload(replayed) != _readiness_comparison_payload(
            readiness
        ):
            errors.append("AI readiness report does not match deterministic replay")
    if errors:
        raise ValueError("; ".join(errors))
    return {
        "status": "c2b_ai_engineering_training_authorization_validated",
        "candidate_id": expected_candidate,
        "protocol_version": AI_TRAINING_PROTOCOL_VERSION,
        "training_authorization_mode": AI_TRAINING_AUTHORIZATION_MODE,
        "engineering_training_authorized": True,
        "formal_training_authorized": False,
        "human_verified": False,
        "ai_quality_gates_passed": readiness["ai_quality_gates_passed"],
        "authorization_sha256": file_sha256(paths["authorization"]),
        "candidate_manifest_sha256": file_sha256(paths["candidate_manifest"]),
        "readiness_report_sha256": file_sha256(paths["readiness_report"]),
        "protocol_lock_sha256": file_sha256(paths["protocol_lock"]),
    }
