from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from intentfence.data import file_sha256
from intentfence.route_b_readiness import evaluate_route_b_readiness

C2B_PROTOCOL_VERSION = "2.0.0"
_C2B_CONSTRUCTION_ROLES = {"train", "validation", "calibration", "test_a"}


def _read_object(path: Path, *, description: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{description} is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{description} must be a JSON object")
    return payload


def _has_timezone(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


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


def _same_path(left: str | Path, right: str | Path) -> bool:
    return os.path.normcase(str(Path(left).resolve())) == os.path.normcase(
        str(Path(right).resolve())
    )


def _require_file(path: Path, description: str, errors: list[str]) -> None:
    if not path.is_file():
        errors.append(f"{description} is missing: {path}")


def _validate_authorization_fields(
    authorization: dict[str, Any],
    *,
    expected_candidate: str,
    candidate_manifest_path: Path,
    readiness_report_path: Path,
    protocol_lock_path: Path,
) -> list[str]:
    errors: list[str] = []
    if authorization.get("schema_version") != 1:
        errors.append("training authorization schema_version must be 1")
    if authorization.get("candidate_id") != expected_candidate:
        errors.append("training authorization candidate_id does not match the expected candidate")
    if authorization.get("protocol_version") != C2B_PROTOCOL_VERSION:
        errors.append(
            f"training authorization protocol_version must be {C2B_PROTOCOL_VERSION}"
        )
    for field in ("human_verified", "formal_training_authorized"):
        if authorization.get(field) is not True:
            errors.append(f"training authorization requires {field}=true")
    if not isinstance(authorization.get("approved_by_project_owner"), str) or not authorization[
        "approved_by_project_owner"
    ].strip():
        errors.append("training authorization requires approved_by_project_owner")
    if not _has_timezone(authorization.get("approved_at")):
        errors.append("training authorization approved_at must include a timezone")

    for field, path, description in (
        (
            "candidate_manifest_sha256",
            candidate_manifest_path,
            "candidate manifest",
        ),
        ("readiness_report_sha256", readiness_report_path, "readiness report"),
        ("protocol_lock_sha256", protocol_lock_path, "protocol lock"),
    ):
        try:
            observed = file_sha256(path)
        except OSError as exc:
            errors.append(f"cannot hash {description}: {exc}")
            continue
        if authorization.get(field) != observed:
            errors.append(f"training authorization {field} does not match {description}")

    return errors


def _validate_training_split_binding(
    candidate_manifest: dict[str, Any],
    *,
    candidate_manifest_path: Path,
    train_path: Path,
    validation_path: Path,
) -> list[str]:
    errors: list[str] = []
    splits = candidate_manifest.get("splits")
    if not isinstance(splits, dict):
        return ["candidate manifest splits are missing"]
    for split_name, observed_path in (
        ("train", train_path),
        ("validation", validation_path),
    ):
        entry = splits.get(split_name)
        if not isinstance(entry, dict):
            errors.append(f"candidate manifest split is missing: {split_name}")
            continue
        relative_path = entry.get("path")
        if not isinstance(relative_path, str) or not relative_path.strip():
            errors.append(f"candidate manifest split path is missing: {split_name}")
            continue
        expected_path = candidate_manifest_path.parent / relative_path
        if not _same_path(observed_path, expected_path):
            errors.append(f"training {split_name} path does not match candidate manifest")
        try:
            observed_sha256 = file_sha256(observed_path)
        except OSError as exc:
            errors.append(f"cannot hash training {split_name} split: {exc}")
            continue
        if entry.get("sha256") != observed_sha256:
            errors.append(f"training {split_name} split hash does not match candidate manifest")
    return errors


def _validate_candidate_manifest_identity(
    candidate_manifest: dict[str, Any],
    *,
    expected_candidate: str,
) -> list[str]:
    errors: list[str] = []
    if candidate_manifest.get("data_version") != expected_candidate:
        errors.append("candidate manifest data_version does not match the expected candidate")
    if candidate_manifest.get("sha256") != _sealed_hash(candidate_manifest):
        errors.append("candidate manifest self-hash mismatch")
    if candidate_manifest.get("formal_training_authorized") is not False:
        errors.append("candidate manifest must keep formal_training_authorized=false")
    splits = candidate_manifest.get("splits")
    if not isinstance(splits, dict) or set(splits) != _C2B_CONSTRUCTION_ROLES:
        errors.append("candidate manifest must contain exactly train/validation/calibration/test_a")
    return errors


def validate_c2b_candidate_inputs(
    *,
    expected_candidate: str,
    candidate_manifest_path: str | Path,
    train_path: str | Path,
    validation_path: str | Path,
) -> dict[str, Any]:
    paths = {
        "candidate_manifest": Path(candidate_manifest_path),
        "train": Path(train_path),
        "validation": Path(validation_path),
    }
    errors: list[str] = []
    for name, path in paths.items():
        _require_file(path, name, errors)
    if errors:
        raise ValueError("; ".join(errors))
    candidate_manifest = _read_object(
        paths["candidate_manifest"], description="candidate manifest"
    )
    errors.extend(
        _validate_candidate_manifest_identity(
            candidate_manifest,
            expected_candidate=expected_candidate,
        )
    )
    errors.extend(
        _validate_training_split_binding(
            candidate_manifest,
            candidate_manifest_path=paths["candidate_manifest"],
            train_path=paths["train"],
            validation_path=paths["validation"],
        )
    )
    if errors:
        raise ValueError("; ".join(errors))
    return {
        "status": "c2b_candidate_preflight_validated",
        "candidate_id": expected_candidate,
        "candidate_manifest_sha256": file_sha256(paths["candidate_manifest"]),
        "train_sha256": file_sha256(paths["train"]),
        "validation_sha256": file_sha256(paths["validation"]),
    }


def _validate_readiness_binding(
    readiness: dict[str, Any],
    *,
    policy_path: Path,
    protocol_document_path: Path,
    protocol_lock_path: Path,
    candidate_manifest_path: Path,
    integrity_report_path: Path,
    audit_analysis_path: Path,
    audit_manifest_path: Path,
    public_report_path: Path,
) -> list[str]:
    errors: list[str] = []
    if readiness.get("status") != "ready_for_project_owner_training":
        errors.append("readiness report is not ready_for_project_owner_training")
    if readiness.get("formal_training_authorized") is not True:
        errors.append("readiness report does not authorize project-owner training")
    if readiness.get("training_executor") != "project_owner_only":
        errors.append("readiness report training executor is not project_owner_only")
    if readiness.get("final_test_lock_remains_active") is not True:
        errors.append("readiness report must keep the final-test lock active")
    if readiness.get("readiness_blockers") != []:
        errors.append("readiness report contains blockers")
    if readiness.get("validation_errors") != []:
        errors.append("readiness report contains validation errors")
    gates = readiness.get("gates")
    if not isinstance(gates, dict) or not gates or not all(value is True for value in gates.values()):
        errors.append("readiness report does not have all gates set to true")

    evidence = readiness.get("evidence")
    expected = {
        "policy": policy_path,
        "protocol_document": protocol_document_path,
        "protocol_lock": protocol_lock_path,
        "candidate_manifest": candidate_manifest_path,
        "integrity_report": integrity_report_path,
        "audit_analysis": audit_analysis_path,
        "audit_manifest": audit_manifest_path,
        "public_report": public_report_path,
    }
    if not isinstance(evidence, dict):
        errors.append("readiness report evidence binding is missing")
    else:
        for name, path in expected.items():
            entry = evidence.get(name)
            if not isinstance(entry, dict):
                errors.append(f"readiness report evidence is missing: {name}")
                continue
            if not _same_path(entry.get("path", ""), path):
                errors.append(f"readiness report evidence path does not match: {name}")
            try:
                observed = file_sha256(path)
            except OSError as exc:
                errors.append(f"cannot hash readiness evidence {name}: {exc}")
                continue
            if entry.get("sha256") != observed:
                errors.append(f"readiness report evidence hash does not match: {name}")

    if errors:
        return errors

    try:
        replayed = evaluate_route_b_readiness(
            policy_path=policy_path,
            protocol_document=protocol_document_path,
            protocol_lock=protocol_lock_path,
            candidate_manifest=candidate_manifest_path,
            integrity_report=integrity_report_path,
            audit_analysis=audit_analysis_path,
            audit_manifest=audit_manifest_path,
            public_report=public_report_path,
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        errors.append(f"readiness report deterministic replay failed: {exc}")
    else:
        if replayed != readiness:
            errors.append("readiness report does not match deterministic replay")
    return errors


def validate_c2b_training_authorization(
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
        _require_file(path, name, errors)
    if errors:
        raise ValueError("; ".join(errors))
    authorization_resolved = paths["authorization"].resolve()
    if any(
        authorization_resolved == path.resolve()
        for name, path in paths.items()
        if name != "authorization"
    ):
        errors.append("training authorization must be a separate file from bound evidence")

    authorization = _read_object(paths["authorization"], description="training authorization")
    candidate_manifest = _read_object(
        paths["candidate_manifest"], description="candidate manifest"
    )
    errors.extend(
        _validate_candidate_manifest_identity(
            candidate_manifest,
            expected_candidate=expected_candidate,
        )
    )
    errors.extend(
        _validate_training_split_binding(
            candidate_manifest,
            candidate_manifest_path=paths["candidate_manifest"],
            train_path=paths["train"],
            validation_path=paths["validation"],
        )
    )
    errors.extend(
        _validate_authorization_fields(
            authorization,
            expected_candidate=expected_candidate,
            candidate_manifest_path=paths["candidate_manifest"],
            readiness_report_path=paths["readiness_report"],
            protocol_lock_path=paths["protocol_lock"],
        )
    )
    readiness = _read_object(paths["readiness_report"], description="readiness report")
    errors.extend(
        _validate_readiness_binding(
            readiness,
            policy_path=paths["policy"],
            protocol_document_path=paths["protocol_document"],
            protocol_lock_path=paths["protocol_lock"],
            candidate_manifest_path=paths["candidate_manifest"],
            integrity_report_path=paths["integrity_report"],
            audit_analysis_path=paths["audit_analysis"],
            audit_manifest_path=paths["audit_manifest"],
            public_report_path=paths["public_report"],
        )
    )
    if errors:
        raise ValueError("; ".join(errors))
    return {
        "status": "c2b_training_authorization_validated",
        "candidate_id": expected_candidate,
        "protocol_version": C2B_PROTOCOL_VERSION,
        "authorization_sha256": file_sha256(paths["authorization"]),
        "candidate_manifest_sha256": file_sha256(paths["candidate_manifest"]),
        "readiness_report_sha256": file_sha256(paths["readiness_report"]),
        "protocol_lock_sha256": file_sha256(paths["protocol_lock"]),
    }
