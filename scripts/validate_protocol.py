"""Validate the C0 preregistration and its pinned source registry."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SHA40 = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_HYPOTHESES = {"H1", "H2", "H3", "H4", "H5"}
REQUIRED_PARTITIONS = {
    "train",
    "validation",
    "calibration",
    "test_a",
    "test_b",
    "test_c",
    "test_d",
}
ALLOWED_TASK_SHIELD_LABELS = {
    "paper-reported",
    "reproduced",
    "Task-Shield-inspired approximation",
}


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return value


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def validate_lock(lock: dict[str, Any], root: Path) -> list[str]:
    """Verify that every candidate-lock hash matches the current file bytes."""
    errors: list[str] = []
    if lock.get("algorithm") != "SHA-256":
        errors.append("protocol lock algorithm must be SHA-256")
    files = lock.get("files", {})
    if not isinstance(files, dict) or not files:
        return [*errors, "protocol lock file list is empty"]
    for relative, expected in files.items():
        path = root / relative
        if not path.is_file():
            errors.append(f"locked protocol file is missing: {relative}")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            errors.append(f"protocol hash mismatch: {relative}")
    return errors


def validate_freeze_consistency(registry: dict[str, Any], lock: dict[str, Any]) -> list[str]:
    """Check approval, execution ownership, and lock metadata agree."""
    errors: list[str] = []
    if lock.get("protocol_version") != registry.get("protocol_version"):
        errors.append("protocol version differs between registry and lock")
    if lock.get("status") != registry.get("status"):
        errors.append("freeze status differs between registry and lock")
    if registry.get("status") == "frozen" and not all(
        registry.get(field) for field in ("approved_at", "approved_by")
    ):
        errors.append("a frozen registry must record approval provenance")
    resources = registry.get("resources", {})
    if resources.get("training_executor") != "project_owner_only":
        errors.append("the project owner must remain the sole training executor")
    prohibited = set(resources.get("codex_must_not_execute", []))
    required_prohibitions = {
        "real_model_weight_updates",
        "tiny_overfit_training",
        "learned_baseline_fitting_on_real_project_data",
        "gpu_rental_or_paid_training_api",
    }
    if not required_prohibitions.issubset(prohibited):
        errors.append("Codex training prohibitions are incomplete")
    return errors


def validate_registry(registry: dict[str, Any], upstream: dict[str, Any], root: Path) -> list[str]:
    """Return human-readable protocol errors; an empty list means valid."""
    errors: list[str] = []

    if registry.get("status") not in {"approval_pending", "frozen", "superseded"}:
        errors.append("registry status must be approval_pending, frozen, or superseded")

    test_lock = registry.get("test_lock", {})
    if not test_lock.get("enabled") or test_lock.get("formal_test_runs_per_protocol") != 1:
        errors.append("formal final-test lock must be enabled and limited to one run")

    hypotheses = registry.get("hypotheses", [])
    ids = [item.get("id") for item in hypotheses if isinstance(item, dict)]
    if set(ids) != REQUIRED_HYPOTHESES or len(ids) != len(REQUIRED_HYPOTHESES):
        errors.append("hypotheses must contain H1-H5 exactly once")
    for item in hypotheses:
        if not isinstance(item, dict):
            errors.append("every hypothesis must be a mapping")
            continue
        comparison = item.get("comparison")
        if not isinstance(comparison, list) or len(comparison) != 2:
            errors.append(f"{item.get('id', '?')} must have one two-arm primary comparison")
        if not item.get("primary_metric") or item.get("direction") not in {
            "less_than_zero",
            "greater_than_zero",
        }:
            errors.append(f"{item.get('id', '?')} needs a primary metric and direction")

    partitions = registry.get("partitions", {})
    partition_names = set(partitions) - {"grouping_rule"}
    if partition_names != REQUIRED_PARTITIONS:
        errors.append("partition registry must define train, validation, calibration, test A-D")
    selection_split = registry.get("selection", {}).get("selection_split")
    if selection_split != "validation":
        errors.append("model selection must use validation only")
    if registry.get("calibration", {}).get("threshold_source") != "calibration_only":
        errors.append("thresholds must be selected on calibration only")

    seeds = registry.get("selection", {}).get("seeds", [])
    if (
        len(seeds) < 3
        or len(set(seeds)) != len(seeds)
        or not all(isinstance(seed, int) for seed in seeds)
    ):
        errors.append("at least three unique integer seeds are required")

    allowed = set(registry.get("task_shield_allowed_labels", []))
    current = registry.get("task_shield_current_label")
    if allowed != ALLOWED_TASK_SHIELD_LABELS or current not in allowed:
        errors.append("Task Shield evidence labels do not match the frozen vocabulary")

    for relative in registry.get("required_protocol_files", []):
        if not (root / relative).is_file():
            errors.append(f"required protocol file is missing: {relative}")

    sources = upstream.get("sources", {})
    if not sources:
        errors.append("upstream source registry is empty")
    for source_id, source in sources.items():
        if not isinstance(source, dict):
            errors.append(f"upstream source {source_id} must be a mapping")
            continue
        if not source.get("official_url"):
            errors.append(f"upstream source {source_id} lacks an official URL")
        if source.get("kind") != "paper":
            if not source.get("license"):
                errors.append(f"upstream source {source_id} lacks a license finding")
            if not SHA40.fullmatch(str(source.get("revision", ""))):
                errors.append(f"upstream source {source_id} lacks a full 40-hex revision")

    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry",
        type=Path,
        default=ROOT / "configs" / "experiment_registry.yaml",
    )
    parser.add_argument(
        "--upstream",
        type=Path,
        default=ROOT / "configs" / "upstream_sources.yaml",
    )
    parser.add_argument(
        "--lock",
        type=Path,
        default=ROOT / "configs" / "protocol_lock.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registry = _load_yaml(args.registry)
    lock = _load_json(args.lock)
    errors = validate_registry(registry, _load_yaml(args.upstream), ROOT)
    errors.extend(validate_lock(lock, ROOT))
    errors.extend(validate_freeze_consistency(registry, lock))
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("C0 protocol validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
