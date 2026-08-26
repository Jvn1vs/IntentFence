from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from intentfence.data import file_sha256
from intentfence.route_b import load_route_b_policy
from intentfence.route_b_audit_analysis import analyze_blind_audits

HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
REQUIRED_REVIEWERS = ("ai_a", "ai_b")


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def _reviewer_identity(reviewer: dict[str, Any]) -> tuple[str, str, str]:
    return tuple(str(reviewer.get(key, "")).strip() for key in ("provider", "model", "revision"))


def _is_placeholder(value: Any) -> bool:
    return not str(value).strip() or "REPLACE" in str(value).upper()


def _validate_ai_manifest(
    manifest: dict[str, Any],
    *,
    metadata_path: Path,
    audit_manifest_path: Path,
    sheet_paths: dict[str, Path],
    policy: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    audit_policy = policy.get("audit", {})
    if manifest.get("schema_version") != 1:
        errors.append("AI review manifest schema_version must be 1")
    if manifest.get("protocol_version") != policy.get("protocol_version"):
        errors.append("AI review manifest protocol_version differs from policy")
    if manifest.get("review_mode") != "dual_ai_engineering":
        errors.append("AI review manifest review_mode must be dual_ai_engineering")
    if manifest.get("content_class") != "synthetic_project_owned":
        errors.append("AI review content_class must be synthetic_project_owned")
    if manifest.get("audit_manifest_sha256") != file_sha256(audit_manifest_path):
        errors.append("AI review manifest is not bound to the audit manifest hash")
    try:
        audit_manifest = _read_json(audit_manifest_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"invalid audit manifest: {exc}")
        audit_manifest = {}
    expected_rows = audit_policy.get("sample_rows", {})
    if audit_manifest.get("risk_rows") != expected_rows.get("risk"):
        errors.append("audit Risk row count differs from the AI protocol")
    if audit_manifest.get("alignment_rows") != expected_rows.get("alignment"):
        errors.append("audit Alignment row count differs from the AI protocol")
    reviewers = manifest.get("reviewers")
    if not isinstance(reviewers, dict) or set(reviewers) != set(REQUIRED_REVIEWERS):
        errors.append("AI review manifest must define exactly ai_a and ai_b")
        reviewers = {}
    identities: list[tuple[str, str, str]] = []
    external_used = False
    for slot in REQUIRED_REVIEWERS:
        reviewer = reviewers.get(slot)
        if not isinstance(reviewer, dict):
            errors.append(f"{slot} metadata is missing")
            continue
        identity = _reviewer_identity(reviewer)
        identities.append(identity)
        if any(_is_placeholder(value) for value in identity):
            errors.append(f"{slot} provider/model/revision must be non-empty")
        if reviewer.get("execution_mode") not in {"local", "external"}:
            errors.append(f"{slot} execution_mode must be local or external")
        external_used = external_used or reviewer.get("execution_mode") == "external"
        if reviewer.get("temperature") != audit_policy.get("temperature_must_equal", 0):
            errors.append(f"{slot} temperature must be exactly zero")
        if reviewer.get("seed_labels_hidden") is not True:
            errors.append(f"{slot} must attest that seed labels were hidden")
        if reviewer.get("other_reviewer_output_hidden") is not True:
            errors.append(f"{slot} must attest that the other AI output was hidden")
        prompt_hash = str(reviewer.get("prompt_sha256", ""))
        if not HEX64.fullmatch(prompt_hash) or _is_placeholder(prompt_hash):
            errors.append(f"{slot} prompt_sha256 must be a 64-character hex digest")
        raw_files = reviewer.get("raw_output_files")
        if not isinstance(raw_files, dict):
            errors.append(f"{slot} raw_output_files is missing")
            continue
        for task in ("risk", "alignment"):
            key = f"{task}_path"
            raw_path = Path(str(raw_files.get(key, "")))
            if not raw_path.is_absolute():
                raw_path = metadata_path.parent / raw_path
            digest_key = f"{task}_sha256"
            claimed = str(raw_files.get(digest_key, ""))
            if not raw_path.is_file():
                errors.append(f"{slot} raw output is missing: {raw_path}")
            elif claimed != file_sha256(raw_path):
                errors.append(f"{slot} raw output hash mismatch: {task}")
            expected_sheet = sheet_paths[f"{slot}_{task}"]
            if raw_path.resolve() != expected_sheet.resolve():
                errors.append(
                    f"{slot} raw {task} output must be the submitted structured sheet"
                )
    if len(identities) == 2 and identities[0] == identities[1]:
        errors.append("ai_a and ai_b must use distinct provider/model/revision identities")
    if external_used and manifest.get("external_upload_approved_by_project_owner") is not True:
        errors.append("external AI use requires explicit project-owner upload approval")
    return errors


def analyze_dual_ai_reviews(
    *,
    reviewer_a_risk: str | Path,
    reviewer_b_risk: str | Path,
    reviewer_a_alignment: str | Path,
    reviewer_b_alignment: str | Path,
    sealed_seed_labels: str | Path,
    audit_manifest: str | Path,
    ai_review_manifest: str | Path,
    policy: dict[str, Any],
) -> dict[str, Any]:
    metadata_path = Path(ai_review_manifest)
    audit_manifest_path = Path(audit_manifest)
    sheet_paths = {
        "ai_a_risk": Path(reviewer_a_risk),
        "ai_b_risk": Path(reviewer_b_risk),
        "ai_a_alignment": Path(reviewer_a_alignment),
        "ai_b_alignment": Path(reviewer_b_alignment),
    }
    try:
        metadata = _read_json(metadata_path)
        metadata_errors = _validate_ai_manifest(
            metadata,
            metadata_path=metadata_path,
            audit_manifest_path=audit_manifest_path,
            sheet_paths=sheet_paths,
            policy=policy,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "schema_version": 1,
            "review_mode": "dual_ai_engineering",
            "evidence_status": "ai_review_invalid",
            "status": "invalid_ai_review_package",
            "validation_errors": [str(exc)],
            "human_verified": False,
            "formal_training_authorized": False,
        }
    if metadata_errors:
        return {
            "schema_version": 1,
            "protocol_version": policy.get("protocol_version"),
            "review_mode": "dual_ai_engineering",
            "evidence_status": "ai_review_invalid",
            "status": "invalid_ai_review_package",
            "validation_errors": metadata_errors,
            "ai_review_manifest": {
                "path": str(metadata_path.resolve()),
                "sha256": file_sha256(metadata_path),
            },
            "human_verified": False,
            "formal_training_authorized": False,
        }

    base = analyze_blind_audits(
        reviewer_a_risk=sheet_paths["ai_a_risk"],
        reviewer_b_risk=sheet_paths["ai_b_risk"],
        reviewer_a_alignment=sheet_paths["ai_a_alignment"],
        reviewer_b_alignment=sheet_paths["ai_b_alignment"],
        sealed_seed_labels=sealed_seed_labels,
        audit_manifest=audit_manifest_path,
        policy=policy,
    )
    if not base.get("validation_errors"):
        expected_ids = {
            "ai_a": base.get("reviewer_ids", {}).get("reviewer_a"),
            "ai_b": base.get("reviewer_ids", {}).get("reviewer_b"),
        }
        for slot, expected_id in expected_ids.items():
            if metadata["reviewers"][slot].get("reviewer_id") != expected_id:
                base["validation_errors"] = base.get("validation_errors", []) + [
                    f"{slot} metadata reviewer_id differs from submitted CSV"
                ]
    ai_quality_passed = (
        base.get("status") in {"quality_gates_passed", "quality_gates_passed_adjudication_required"}
        and base.get("quality_gates_passed") is True
        and base.get("adjudication_required") is False
    )
    status = "ai_quality_gates_passed_engineering_only" if ai_quality_passed else (
        "ai_quality_gates_failed_engineering_only"
        if base.get("validation_errors") == []
        else "invalid_ai_review_package"
    )
    return {
        "schema_version": 1,
        "protocol_version": policy.get("protocol_version"),
        "review_mode": "dual_ai_engineering",
        "evidence_status": "ai_reviewed_engineering_only",
        "status": status,
        "validation_errors": base.get("validation_errors", []),
        "ai_review_manifest": {
            "path": str(metadata_path.resolve()),
            "sha256": file_sha256(metadata_path),
        },
        "audit_manifest": base.get("audit_manifest"),
        "ai_reviewer_ids": base.get("reviewer_ids"),
        "ai_reviewer_models": {
            slot: {
                key: metadata["reviewers"][slot][key]
                for key in ("provider", "model", "revision", "execution_mode")
            }
            for slot in REQUIRED_REVIEWERS
        },
        "construct_agreement_metrics": base.get("metrics"),
        "quality_gates": base.get("quality_gates", {}),
        "quality_gates_passed": base.get("quality_gates_passed") is True,
        "human_verified": False,
        "formal_training_authorized": False,
        "limitations": [
            "AI agreement is consistency evidence, not independent human validation.",
            "Seed agreement is construct agreement with a synthetic generator, not ground truth accuracy.",
            "Provider/model/prompt drift and shared model bias remain possible.",
        ],
    }


def load_ai_review_policy(path: str | Path) -> dict[str, Any]:
    return load_route_b_policy(path)
