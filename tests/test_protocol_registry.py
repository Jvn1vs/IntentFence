from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

from intentfence.c2b_config import validate_c2b_config

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


def test_c2b_entrypoint_requires_frozen_route_b_protocol() -> None:
    script = (ROOT / "scripts" / "run_c2b_base.ps1").read_text(encoding="utf-8")

    assert "validate_c2b_config.py" in script
    assert "validate_c2b_preflight.py" in script
    assert "validate_c2b_training_authorization.py" in script
    assert "$ProtocolLockPath" in script
    assert "--protocol-lock" in script
    assert "$ReadinessReportPath" in script
    assert "--readiness-report" in script
    assert "--train-path" in script
    assert "--validation-path" in script
    assert "--c2b-authorization-file" in script
    assert '"This C2b entrypoint only supports $SupportedCandidate."' in script
    assert "-PreflightOnly" in script


def test_c2b_registered_configs_are_frozen() -> None:
    for path in sorted((ROOT / "configs").glob("deberta_base_*.yaml")):
        payload = validate_c2b_config(path)
        assert payload["model_revision"] == "8ccc9b6f36199bec6961081d44eb72fb3f7353f3"


def test_c2b_config_rejects_hyperparameter_drift(tmp_path: Path) -> None:
    source = ROOT / "configs" / "deberta_base_action_risk.yaml"
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    payload["learning_rate"] = 1.0e-5
    candidate = tmp_path / source.name
    candidate.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="learning_rate"):
        validate_c2b_config(candidate)
