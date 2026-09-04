from __future__ import annotations

import json
from pathlib import Path

import pytest

from intentfence.run_manifest import (
    build_run_manifest,
    record_actual_cost,
    sha256_file,
    write_run_manifest,
)


def test_run_manifest_records_inputs_environment_and_checkpoint_hashes(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    train_path = tmp_path / "train.jsonl"
    validation_path = tmp_path / "validation.jsonl"
    checkpoint_dir = tmp_path / "best"
    checkpoint_dir.mkdir()
    config_path.write_text(
        "\n".join(
            (
                "run_name: fixture",
                "model_name: microsoft/deberta-v3-small",
                "model_revision: a36c739020e01763fe789b4b85e2df55d6180012",
                "input_mode: action",
                "seed: 42",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    train_path.write_text('{"fixture": "train"}\n', encoding="utf-8")
    validation_path.write_text('{"fixture": "validation"}\n', encoding="utf-8")
    metadata_path = checkpoint_dir / "metadata.json"
    metadata_path.write_text("{}\n", encoding="utf-8")

    payload = build_run_manifest(
        repository_root=Path.cwd(),
        config_path=config_path,
        train_path=train_path,
        validation_path=validation_path,
        checkpoint_dir=checkpoint_dir,
        started_at="2026-08-27T07:00:00Z",
        ended_at="2026-08-27T07:01:00Z",
        duration_seconds=60.0,
        cost_usd=0.0,
    )
    output_path = tmp_path / "run_manifest.json"
    write_run_manifest(payload, output_path)
    loaded = json.loads(output_path.read_text(encoding="utf-8"))

    assert loaded["configuration"]["model_revision"].startswith("a36c739")
    assert loaded["data"]["train"]["sha256"] == sha256_file(train_path)
    assert loaded["checkpoint_files"]["metadata.json"]["bytes"] == metadata_path.stat().st_size
    assert loaded["environment"]["python"]
    assert loaded["environment"]["system_memory_bytes"]
    assert "cuda_available" in loaded["environment"]["accelerator"]
    assert loaded["executor"] == "project_owner"
    assert loaded["cost_usd"] == 0.0


def test_run_manifest_binds_cost_stage_and_authorization(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    train_path = tmp_path / "train.jsonl"
    validation_path = tmp_path / "validation.jsonl"
    checkpoint_dir = tmp_path / "best"
    authorization_path = tmp_path / "authorization.json"
    checkpoint_dir.mkdir()
    config_path.write_text(
        "run_name: fixture\nmodel_name: microsoft/deberta-v3-base\n"
        "model_revision: 8ccc9b6f36199bec6961081d44eb72fb3f7353f3\n"
        "input_mode: action\nseed: 42\n",
        encoding="utf-8",
    )
    train_path.write_text("{}\n", encoding="utf-8")
    validation_path.write_text("{}\n", encoding="utf-8")
    (checkpoint_dir / "metadata.json").write_text("{}\n", encoding="utf-8")
    authorization_path.write_text('{"formal_training_authorized": true}\n', encoding="utf-8")

    payload = build_run_manifest(
        repository_root=Path.cwd(),
        config_path=config_path,
        train_path=train_path,
        validation_path=validation_path,
        checkpoint_dir=checkpoint_dir,
        started_at="2026-08-31T00:00:00Z",
        ended_at="2026-08-31T00:01:00Z",
        duration_seconds=60.0,
        cost_usd=0.0,
        cost_cny=12.5,
        stage="c2b_base",
        authorization_path=authorization_path,
    )

    assert payload["actual_cost_cny"] == 12.5
    assert payload["stage"] == "c2b_base"
    assert payload["training_authorization"]["sha256"] == sha256_file(authorization_path)

    with pytest.raises(ValueError, match="cost_cny cannot be negative"):
        build_run_manifest(
            repository_root=Path.cwd(),
            config_path=config_path,
            train_path=train_path,
            validation_path=validation_path,
            checkpoint_dir=checkpoint_dir,
            started_at="2026-08-31T00:00:00Z",
            ended_at="2026-08-31T00:01:00Z",
            duration_seconds=60.0,
            cost_usd=0.0,
            cost_cny=-1.0,
        )


def test_run_cost_can_be_recorded_after_completed_manifest(tmp_path: Path) -> None:
    manifest_path = tmp_path / "run_manifest.json"
    manifest_path.write_text(
        json.dumps({"schema_version": 1, "status": "completed"}) + "\n",
        encoding="utf-8",
    )

    payload = record_actual_cost(manifest_path, 4.36)
    loaded = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert payload["actual_cost_cny"] == 4.36
    assert loaded["actual_cost_cny"] == 4.36
    assert loaded["cost_recorded_at"]
    assert not (tmp_path / ".run_manifest.json.tmp").exists()

    with pytest.raises(ValueError, match="already recorded"):
        record_actual_cost(manifest_path, 5.00)
