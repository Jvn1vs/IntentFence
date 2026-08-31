from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from intentfence.run_manifest import sha256_file
from intentfence.schema import read_jsonl

FINAL_TEST_SPLITS = ("test_a", "test_b", "test_c")


def artifact_tree_sha256(path: str | Path) -> str:
    """Hash a directory's relative file names and bytes deterministically."""

    root = Path(path)
    if not root.is_dir():
        raise FileNotFoundError(f"model artifact directory does not exist: {root}")
    digest = hashlib.sha256()
    files = [item for item in root.rglob("*") if item.is_file()]
    for item in sorted(files, key=lambda value: value.relative_to(root).as_posix()):
        relative = item.relative_to(root).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        with item.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def _has_timezone(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _read_object(path: Path, *, description: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{description} must be valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{description} must be a JSON object: {path}")
    return payload


def validate_final_test_authorization(
    authorization_path: str | Path,
    *,
    registry_path: str | Path,
    model_dir: str | Path,
    calibration_path: str | Path,
    calibration_report_path: str | Path,
    test_inputs: dict[str, str | Path],
    attack_threshold: float,
) -> dict[str, Any]:
    """Validate a project-owner authorization for one immutable Test A/B/C matrix."""

    authorization_path = Path(authorization_path)
    registry_path = Path(registry_path)
    model_dir = Path(model_dir)
    calibration_path = Path(calibration_path)
    calibration_report_path = Path(calibration_report_path)
    if not math.isfinite(attack_threshold) or not 0 <= attack_threshold <= 1:
        raise ValueError("attack_threshold must be a finite value in [0, 1]")
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    if not isinstance(registry, dict) or registry.get("status") != "frozen":
        raise ValueError("final-test authorization requires a frozen experiment registry")
    protocol_version = str(registry.get("protocol_version", ""))
    test_lock = registry.get("test_lock", {})
    if test_lock.get("enabled") is not True or test_lock.get("formal_test_runs_per_protocol") != 1:
        raise ValueError("frozen registry must enforce exactly one formal test run")

    payload = _read_object(authorization_path, description="final-test authorization")
    if payload.get("formal_final_test_authorized") is not True:
        raise ValueError("authorization requires formal_final_test_authorized=true")
    if payload.get("human_verified") is not True:
        raise ValueError("authorization requires independent human_verified=true")
    if payload.get("final_test_lock_preserved") is not True:
        raise ValueError("authorization must preserve the final-test lock")
    if payload.get("protocol_version") != protocol_version:
        raise ValueError("authorization protocol_version does not match the frozen registry")
    if not isinstance(payload.get("approved_by_project_owner"), str) or not payload[
        "approved_by_project_owner"
    ].strip():
        raise ValueError("authorization requires approved_by_project_owner")
    if not _has_timezone(payload.get("approved_at")):
        raise ValueError("authorization approved_at must include a timezone")

    expected_splits = list(FINAL_TEST_SPLITS)
    if payload.get("test_splits") != expected_splits:
        raise ValueError(f"authorization test_splits must be exactly {expected_splits}")
    if not math.isclose(
        float(payload.get("frozen_attack_threshold", math.nan)),
        attack_threshold,
        rel_tol=0.0,
        abs_tol=1e-15,
    ):
        raise ValueError("authorization frozen_attack_threshold does not match the run")
    if payload.get("model_dir") != str(model_dir.resolve()):
        raise ValueError("authorization model_dir does not match the run")
    if payload.get("model_artifact_sha256") != artifact_tree_sha256(model_dir):
        raise ValueError("authorization model_artifact_sha256 does not match the model directory")
    if payload.get("calibration_path") != str(calibration_path.resolve()):
        raise ValueError("authorization calibration_path does not match the run")
    if payload.get("calibration_sha256") != sha256_file(calibration_path):
        raise ValueError("authorization calibration_sha256 does not match the calibration file")
    if payload.get("calibration_report_path") != str(calibration_report_path.resolve()):
        raise ValueError("authorization calibration_report_path does not match the run")
    if payload.get("calibration_report_sha256") != sha256_file(calibration_report_path):
        raise ValueError("authorization calibration_report_sha256 does not match the report")
    calibration_report = _read_object(
        calibration_report_path, description="calibration report"
    )
    if calibration_report.get("threshold_source") != "calibration_only":
        raise ValueError("calibration report threshold_source must be calibration_only")
    if not math.isclose(
        float(calibration_report.get("frozen_attack_threshold", math.nan)),
        attack_threshold,
        rel_tol=0.0,
        abs_tol=1e-15,
    ):
        raise ValueError("calibration report threshold does not match the run")

    recorded_paths = payload.get("test_input_paths")
    recorded_hashes = payload.get("test_input_sha256")
    expected_paths = {split: str(Path(path).resolve()) for split, path in test_inputs.items()}
    expected_hashes = {split: sha256_file(path) for split, path in test_inputs.items()}
    if set(expected_paths) != set(FINAL_TEST_SPLITS):
        raise ValueError(f"test_inputs must contain exactly {list(FINAL_TEST_SPLITS)}")
    sample_ids: set[str] = set()
    template_groups: set[str] = set()
    for split, path in sorted(test_inputs.items()):
        samples = read_jsonl(path)
        if not samples:
            raise ValueError(f"{split} input is empty")
        wrong_split = [sample.sample_id for sample in samples if sample.split != split]
        if wrong_split:
            raise ValueError(
                f"{split} input contains samples assigned to another split: {wrong_split[:5]}"
            )
        current_ids = {sample.sample_id for sample in samples}
        if sample_ids & current_ids:
            raise ValueError(f"final test inputs share sample IDs across splits: {sorted(sample_ids & current_ids)[:5]}")
        sample_ids.update(current_ids)
        current_groups = {sample.template_group for sample in samples}
        if template_groups & current_groups:
            raise ValueError("final test inputs share template_group values across splits")
        template_groups.update(current_groups)
    if recorded_paths != expected_paths:
        raise ValueError("authorization test_input_paths do not match the run")
    if recorded_hashes != expected_hashes:
        raise ValueError("authorization test_input_sha256 values do not match the run")
    return payload


def claim_final_test_ledger(
    ledger_path: str | Path,
    *,
    authorization_path: str | Path,
    registry_path: str | Path,
    model_dir: str | Path,
    calibration_path: str | Path,
    calibration_report_path: str | Path,
    test_inputs: dict[str, str | Path],
    attack_threshold: float,
    run_id: str,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Atomically claim the one formal final-test matrix; an existing ledger is fatal."""

    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("run_id must be non-empty")
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite final-test output directory: {output_dir}")
    authorization = validate_final_test_authorization(
        authorization_path,
        registry_path=registry_path,
        model_dir=model_dir,
        calibration_path=calibration_path,
        calibration_report_path=calibration_report_path,
        test_inputs=test_inputs,
        attack_threshold=attack_threshold,
    )
    ledger_path = Path(ledger_path)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "status": "claimed",
        "run_id": run_id,
        "claimed_at": datetime.now(timezone.utc).isoformat(),
        "protocol_version": authorization["protocol_version"],
        "test_splits": list(FINAL_TEST_SPLITS),
        "attack_threshold": attack_threshold,
        "authorization_path": str(Path(authorization_path).resolve()),
        "authorization_sha256": sha256_file(authorization_path),
        "model_dir": str(Path(model_dir).resolve()),
        "model_artifact_sha256": artifact_tree_sha256(model_dir),
        "calibration_path": str(Path(calibration_path).resolve()),
        "calibration_sha256": sha256_file(calibration_path),
        "calibration_report_path": str(Path(calibration_report_path).resolve()),
        "calibration_report_sha256": sha256_file(calibration_report_path),
        "test_input_paths": {
            split: str(Path(path).resolve()) for split, path in sorted(test_inputs.items())
        },
        "test_input_sha256": {
            split: sha256_file(path) for split, path in sorted(test_inputs.items())
        },
        "output_dir": str(output_dir.resolve()),
    }
    try:
        with ledger_path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    except FileExistsError as exc:
        raise FileExistsError(
            f"final-test ledger already exists; refusing a second formal matrix: {ledger_path}"
        ) from exc
    return payload


def complete_final_test_ledger(
    ledger_path: str | Path, *, run_id: str, result_paths: dict[str, str | Path]
) -> dict[str, Any]:
    """Mark a claimed matrix complete only after all three result directories exist."""

    ledger_path = Path(ledger_path)
    payload = _read_object(ledger_path, description="final-test ledger")
    if payload.get("status") != "claimed" or payload.get("run_id") != run_id:
        raise ValueError("final-test ledger is not a matching claimed run")
    if set(result_paths) != set(FINAL_TEST_SPLITS):
        raise ValueError(f"result_paths must contain exactly {list(FINAL_TEST_SPLITS)}")
    result_files: dict[str, dict[str, str]] = {}
    for split, path in sorted(result_paths.items()):
        result_dir = Path(path)
        if not result_dir.is_dir():
            raise FileNotFoundError(f"final-test result directory does not exist: {result_dir}")
        files = [item for item in result_dir.rglob("*") if item.is_file()]
        result_files[split] = {
            item.relative_to(result_dir).as_posix(): sha256_file(item)
            for item in sorted(files, key=lambda value: value.relative_to(result_dir).as_posix())
        }
    payload["status"] = "completed"
    payload["completed_at"] = datetime.now(timezone.utc).isoformat()
    payload["result_files"] = result_files
    ledger_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload
