from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from intentfence.constants import RISK_LABELS, TASK_ALIGNMENT_LABELS
from intentfence.deployment import (
    EXPORT_INT8_FILENAME,
    build_export_metadata,
    validate_export_artifacts,
    validate_export_inputs,
    validate_model_directory,
    write_export_metadata,
)

MODEL_REVISION = "a36c739020e01763fe789b4b85e2df55d6180012"


def _model_fixture(tmp_path: Path) -> Path:
    model_dir = tmp_path / "model"
    (model_dir / "encoder").mkdir(parents=True)
    (model_dir / "tokenizer").mkdir()
    (model_dir / "encoder" / "config.json").write_text("{}\n", encoding="utf-8")
    (model_dir / "tokenizer" / "tokenizer.json").write_text("{}\n", encoding="utf-8")
    (model_dir / "heads.pt").write_bytes(b"fixture heads")
    (model_dir / "metadata.json").write_text(
        json.dumps(
            {
                "model_name": "fixture-model",
                "risk_labels": list(RISK_LABELS),
                "input_mode": "action",
                "max_length": 384,
                "alignment_loss_weight": 0.5,
                "model_revision": MODEL_REVISION,
                "version": "3",
                "alignment_labels": list(TASK_ALIGNMENT_LABELS),
                "alignment_target": "task_alignment",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return model_dir


def test_export_preflight_is_read_only_and_refuses_existing_output(tmp_path: Path) -> None:
    model_dir = _model_fixture(tmp_path)
    source_metadata = validate_export_inputs(model_dir, tmp_path / "new-export", opset=17)
    assert source_metadata["model_revision"] == MODEL_REVISION
    assert not (tmp_path / "new-export").exists()

    existing = tmp_path / "existing-export"
    existing.mkdir()
    with pytest.raises(FileExistsError, match="overwrite"):
        validate_export_inputs(model_dir, existing, opset=17)


def test_export_script_preflight_does_not_create_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from deployment import export_onnx

    model_dir = _model_fixture(tmp_path)
    output_dir = tmp_path / "script-export"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "export_onnx.py",
            "--model-dir",
            str(model_dir),
            "--output-dir",
            str(output_dir),
            "--preflight-only",
        ],
    )

    export_onnx.main()

    assert not output_dir.exists()


def test_export_metadata_binds_fp32_int8_and_tokenizer_hashes(tmp_path: Path) -> None:
    model_dir = _model_fixture(tmp_path)
    output_dir = tmp_path / "export"
    (output_dir / "tokenizer").mkdir(parents=True)
    (output_dir / "tokenizer" / "tokenizer.json").write_text("{}\n", encoding="utf-8")
    (output_dir / "model.onnx").write_bytes(b"fixture fp32")
    (output_dir / EXPORT_INT8_FILENAME).write_bytes(b"fixture int8")
    payload = build_export_metadata(
        output_dir,
        model_dir,
        model_metadata=validate_model_directory(model_dir),
        opset=17,
        quantized_path=output_dir / EXPORT_INT8_FILENAME,
    )
    write_export_metadata(output_dir, payload)

    validated = validate_export_artifacts(output_dir, model_path=output_dir / EXPORT_INT8_FILENAME)
    assert validated["source_model"]["model_revision"] == MODEL_REVISION
    assert validated["export"]["quantization"] == "dynamic_weight_qint8"

    (output_dir / EXPORT_INT8_FILENAME).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="artifacts.int8.sha256"):
        validate_export_artifacts(output_dir)


def test_model_directory_requires_frozen_revision_and_labels(tmp_path: Path) -> None:
    model_dir = _model_fixture(tmp_path)
    payload = json.loads((model_dir / "metadata.json").read_text(encoding="utf-8"))
    payload["model_revision"] = "main"
    (model_dir / "metadata.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="40-character revision"):
        validate_model_directory(model_dir)


def test_docker_deployment_has_context_and_runtime_safety_contract() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    dockerignore = (repository_root / ".dockerignore").read_text(encoding="utf-8")
    dockerfile = (repository_root / "deployment" / "Dockerfile").read_text(encoding="utf-8")

    assert all(entry in dockerignore.splitlines() for entry in ("data", "checkpoints", "artifacts"))
    assert all(entry in dockerignore.splitlines() for entry in ("runs", "wandb", "mlruns", "reports"))
    assert "USER 65532:65532" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "/health" in dockerfile
