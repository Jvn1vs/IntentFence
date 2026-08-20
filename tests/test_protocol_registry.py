from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "validate_protocol.py"


def _load_validator():
    spec = importlib.util.spec_from_file_location("validate_protocol", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_yaml(path: Path):
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def test_c0_registry_is_valid() -> None:
    validator = _load_validator()
    registry = _load_yaml(ROOT / "configs" / "experiment_registry.yaml")
    upstream = _load_yaml(ROOT / "configs" / "upstream_sources.yaml")

    assert validator.validate_registry(registry, upstream, ROOT) == []


def test_protocol_candidate_hashes_are_current() -> None:
    validator = _load_validator()
    with (ROOT / "configs" / "protocol_lock.json").open(encoding="utf-8") as handle:
        lock = json.load(handle)

    assert validator.validate_lock(lock, ROOT) == []
    registry = _load_yaml(ROOT / "configs" / "experiment_registry.yaml")
    assert validator.validate_freeze_consistency(registry, lock) == []


def test_validator_rejects_test_based_threshold_selection() -> None:
    validator = _load_validator()
    registry = _load_yaml(ROOT / "configs" / "experiment_registry.yaml")
    upstream = _load_yaml(ROOT / "configs" / "upstream_sources.yaml")
    registry["calibration"]["threshold_source"] = "test_a"

    errors = validator.validate_registry(registry, upstream, ROOT)

    assert "thresholds must be selected on calibration only" in errors


def test_validator_rejects_codex_as_training_executor() -> None:
    validator = _load_validator()
    registry = _load_yaml(ROOT / "configs" / "experiment_registry.yaml")
    with (ROOT / "configs" / "protocol_lock.json").open(encoding="utf-8") as handle:
        lock = json.load(handle)
    registry["resources"]["training_executor"] = "codex"

    errors = validator.validate_freeze_consistency(registry, lock)

    assert "the project owner must remain the sole training executor" in errors
