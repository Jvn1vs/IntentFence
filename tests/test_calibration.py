from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from intentfence.calibration import (
    MultiHeadCalibration,
    TemperatureScaler,
    calibration_bundle_marker_path,
    load_calibration_arrays,
    load_calibration_protocol_snapshot,
    load_policy_snapshot,
    validate_calibration_arrays,
    validate_calibration_authorization,
    validate_calibration_export_authorization,
)
from intentfence.constants import RISK_LABELS, TASK_ALIGNMENT_LABELS
from intentfence.run_manifest import artifact_tree_sha256, sha256_file


def _write_logits_bundle(tmp_path, *, split: str = "calibration"):
    input_path = tmp_path / "calibration.jsonl"
    logits_path = tmp_path / "logits.npz"
    model_dir = tmp_path / "frozen-model"
    model_dir.mkdir()
    (model_dir / "weights.bin").write_bytes(b"synthetic frozen model")
    risk_logits = np.array(
        [
            [4.0, 0.0, -1.0, -2.0, -3.0],
            [0.0, 4.0, -1.0, -2.0, -3.0],
            [0.0, -1.0, 4.0, -2.0, -3.0],
            [0.0, -1.0, -2.0, 4.0, -3.0],
            [0.0, -1.0, -2.0, -3.0, 4.0],
            [3.0, 0.0, -1.0, -2.0, -3.0],
            [0.0, 3.0, -1.0, -2.0, -3.0],
            [0.0, -1.0, 3.0, -2.0, -3.0],
            [0.0, -1.0, -2.0, 3.0, -3.0],
            [0.0, -1.0, -2.0, -3.0, 3.0],
        ]
    )
    alignment_logits = np.array(
        [
            [4.0, 0.0, -1.0, -2.0],
            [0.0, 4.0, -1.0, -2.0],
            [-1.0, 0.0, 4.0, -2.0],
            [-1.0, 0.0, -2.0, 4.0],
            [4.0, 0.0, -1.0, -2.0],
            [0.0, 4.0, -1.0, -2.0],
            [-1.0, 0.0, 4.0, -2.0],
            [-1.0, 0.0, -2.0, 4.0],
            [4.0, 0.0, -1.0, -2.0],
            [0.0, 4.0, -1.0, -2.0],
        ]
    )
    risk_labels = np.array([0, 1, 2, 3, 4, 0, 1, 2, 3, 4])
    alignment_labels = np.array([0, 1, 2, 3, 0, 1, 2, 3, 0, 1])
    input_path.write_text(
        "".join(
            json.dumps(
                {
                    "sample_id": f"calibration-{index}",
                    "source": "synthetic",
                    "untrusted_content": f"synthetic calibration fixture {index}",
                    "risk_label": RISK_LABELS[int(risk_label)],
                    "alignment_label": 0 if risk_label == 0 else 1,
                    "task_alignment_label": TASK_ALIGNMENT_LABELS[int(alignment_label)],
                    "template_group": f"calibration-fixture-group-{index}",
                    "split": "calibration",
                    "action_provenance": "missing",
                    "adapter_missing_action": True,
                }
            )
            + "\n"
            for index, (risk_label, alignment_label) in enumerate(
                zip(risk_labels, alignment_labels, strict=True)
            )
        ),
        encoding="utf-8",
    )
    np.savez_compressed(
        logits_path,
        risk_logits=risk_logits,
        alignment_logits=alignment_logits,
        risk_labels=risk_labels,
        alignment_labels=alignment_labels,
    )
    metadata_path = logits_path.with_suffix(".json")
    metadata_path.write_text(
        json.dumps(
            {
                "format_version": 3,
                "input": str(input_path.resolve()),
                "input_sha256": sha256_file(input_path),
                "model_dir": str(model_dir.resolve()),
                "model_artifact_sha256": artifact_tree_sha256(model_dir),
                "model_revision": "fixture-model-revision",
                "logits_sha256": sha256_file(logits_path),
                "split": split,
                "samples": len(risk_labels),
                "sample_ids": [f"calibration-{index}" for index in range(len(risk_labels))],
                "template_groups": [
                    f"calibration-fixture-group-{index}" for index in range(len(risk_labels))
                ],
                "risk_labels": list(RISK_LABELS),
                "risk_logits_shape": list(risk_logits.shape),
                "alignment_logits_shape": list(alignment_logits.shape),
                "alignment_labels": list(TASK_ALIGNMENT_LABELS),
                "alignment_target": "task_alignment",
            }
        ),
        encoding="utf-8",
    )
    calibration_bundle_marker_path(logits_path).write_text(
        json.dumps(
            {
                "format_version": 1,
                "logits_path": str(logits_path.resolve()),
                "metadata_path": str(metadata_path.resolve()),
                "logits_sha256": sha256_file(logits_path),
                "metadata_sha256": sha256_file(metadata_path),
            }
        ),
        encoding="utf-8",
    )
    return logits_path, metadata_path


def _authorization_payload(logits_path: Path, metadata: dict) -> dict:
    policy_path = Path(__file__).resolve().parents[1] / "configs" / "policy.yaml"
    policy = load_policy_snapshot(policy_path)
    protocol_path = Path(__file__).resolve().parents[1] / "configs" / "experiment_registry.yaml"
    protocol = load_calibration_protocol_snapshot(protocol_path)
    return {
        "schema_version": 1,
        "calibration_authorized": True,
        "human_verified": True,
        "final_test_lock_preserved": True,
        "approved_by_project_owner": "fixture-owner",
        "approved_at": "2026-08-31T12:00:00+08:00",
        "target_fpr": 0.01,
        "logits_sha256": sha256_file(logits_path),
        "metadata_path": str(logits_path.with_suffix(".json").resolve()),
        "metadata_sha256": sha256_file(logits_path.with_suffix(".json")),
        "input": metadata["input"],
        "input_sha256": metadata["input_sha256"],
        "model_dir": metadata["model_dir"],
        "model_artifact_sha256": metadata["model_artifact_sha256"],
        "model_revision": metadata["model_revision"],
        "policy_path": policy["path"],
        "policy_sha256": policy["sha256"],
        "policy_version": policy["version"],
        "protocol_registry_path": protocol["path"],
        "protocol_registry_sha256": protocol["sha256"],
        "protocol_version": protocol["protocol_version"],
        "minimum_viable_attack_tpr": protocol["minimum_viable_attack_tpr"],
    }


def test_calibration_bundle_requires_hash_verified_calibration_sidecar(tmp_path):
    logits_path, metadata_path = _write_logits_bundle(tmp_path)

    arrays, metadata = load_calibration_arrays(logits_path)

    assert metadata["split"] == "calibration"
    assert validate_calibration_arrays(arrays) == {
        "samples": 10,
        "risk_classes": 5,
        "alignment_classes": 4,
    }
    assert metadata_path.exists()


def test_calibration_bundle_rejects_wrong_split_and_hash(tmp_path):
    logits_path, metadata_path = _write_logits_bundle(tmp_path, split="validation")
    with pytest.raises(ValueError, match="split='calibration'"):
        load_calibration_arrays(logits_path)

    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload["split"] = "calibration"
    payload["input_sha256"] = "0" * 64
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")
    marker_path = calibration_bundle_marker_path(logits_path)
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker["metadata_sha256"] = sha256_file(metadata_path)
    marker_path.write_text(json.dumps(marker), encoding="utf-8")
    with pytest.raises(ValueError, match="input hash"):
        load_calibration_arrays(logits_path)


def test_temperature_scaler_rejects_degenerate_or_nonfinite_inputs():
    with pytest.raises(ValueError, match="finite"):
        TemperatureScaler().fit(np.array([[np.inf, 0.0], [0.0, 1.0]]), np.array([0, 1]))
    with pytest.raises(ValueError, match="two label classes"):
        TemperatureScaler().fit(np.zeros((2, 2)), np.array([0, 0]))


def test_calibration_authorization_is_bound_to_logits_and_input(tmp_path):
    logits_path, _ = _write_logits_bundle(tmp_path)
    _, metadata = load_calibration_arrays(logits_path)
    authorization_path = tmp_path / "calibration_authorization.json"
    authorization_payload = _authorization_payload(logits_path, metadata)
    authorization_payload["approved_by_project_owner"] = "owner"
    authorization_path.write_text(json.dumps(authorization_payload), encoding="utf-8")

    payload = validate_calibration_authorization(
        authorization_path,
        logits_path=logits_path,
        metadata=metadata,
        metadata_path=logits_path.with_suffix(".json"),
        policy_snapshot=load_policy_snapshot(
            Path(__file__).resolve().parents[1] / "configs" / "policy.yaml"
        ),
        protocol_snapshot=load_calibration_protocol_snapshot(
            Path(__file__).resolve().parents[1] / "configs" / "experiment_registry.yaml"
        ),
        target_fpr=0.01,
    )

    assert payload["approved_by_project_owner"] == "owner"
    payload["logits_sha256"] = "0" * 64
    authorization_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="logits_sha256"):
        validate_calibration_authorization(
            authorization_path,
            logits_path=logits_path,
            metadata=metadata,
            metadata_path=logits_path.with_suffix(".json"),
            policy_snapshot=load_policy_snapshot(
                Path(__file__).resolve().parents[1] / "configs" / "policy.yaml"
            ),
            protocol_snapshot=load_calibration_protocol_snapshot(
                Path(__file__).resolve().parents[1] / "configs" / "experiment_registry.yaml"
            ),
            target_fpr=0.01,
        )


def test_calibration_save_refuses_overwrite(tmp_path):
    calibration = MultiHeadCalibration(TemperatureScaler(), TemperatureScaler())
    output = tmp_path / "calibration.json"
    calibration.save(output)
    with pytest.raises(FileExistsError, match="overwrite"):
        calibration.save(output)


def test_calibration_cli_preflight_is_read_only(tmp_path):
    logits_path, _ = _write_logits_bundle(tmp_path)
    output = tmp_path / "calibration.json"
    report = tmp_path / "calibration_report.json"
    repository_root = Path(__file__).resolve().parents[1]

    result = subprocess.run(
        [
            sys.executable,
            "scripts/calibrate.py",
            "--logits",
            str(logits_path),
            "--output",
            str(output),
            "--report",
            str(report),
            "--preflight-only",
        ],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "preflight_passed"
    assert not output.exists()
    assert not report.exists()


def test_calibration_cli_requires_owner_authorization_before_fitting(tmp_path):
    logits_path, _ = _write_logits_bundle(tmp_path)
    output = tmp_path / "calibration.json"
    report = tmp_path / "calibration_report.json"
    repository_root = Path(__file__).resolve().parents[1]

    result = subprocess.run(
        [
            sys.executable,
            "scripts/calibrate.py",
            "--logits",
            str(logits_path),
            "--output",
            str(output),
            "--report",
            str(report),
        ],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "authorization is required" in result.stderr
    assert not output.exists()
    assert not report.exists()


def test_export_logits_cli_preflight_requires_explicit_calibration_split(tmp_path):
    input_path = tmp_path / "samples.jsonl"
    input_path.write_text(
        json.dumps(
            {
                "sample_id": "cal-1",
                "source": "synthetic",
                "untrusted_content": "fixture",
                "risk_label": "benign",
                "alignment_label": 0,
                "template_group": "fixture-group",
                "split": "calibration",
                "action_provenance": "missing",
                "adapter_missing_action": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "export.npz"
    repository_root = Path(__file__).resolve().parents[1]

    result = subprocess.run(
        [
            sys.executable,
            "scripts/export_logits.py",
            "--input",
            str(input_path),
            "--output",
            str(output),
            "--preflight-only",
        ],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "preflight_passed"
    assert payload["split"] == "calibration"
    assert not output.exists()
    assert not output.with_suffix(".json").exists()


def test_calibration_cli_writes_a_complete_synthetic_report(tmp_path):
    logits_path, _ = _write_logits_bundle(tmp_path)
    _, metadata = load_calibration_arrays(logits_path)
    authorization_path = tmp_path / "authorization.json"
    authorization_path.write_text(
        json.dumps(_authorization_payload(logits_path, metadata)), encoding="utf-8"
    )
    output = tmp_path / "calibration.json"
    report = tmp_path / "report.json"
    repository_root = Path(__file__).resolve().parents[1]

    result = subprocess.run(
        [
            sys.executable,
            "scripts/calibrate.py",
            "--logits",
            str(logits_path),
            "--output",
            str(output),
            "--report",
            str(report),
            "--authorization-file",
            str(authorization_path),
            "--n-bins",
            "4",
            "--classwise-min-samples",
            "2",
        ],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    report_payload = json.loads(report.read_text(encoding="utf-8"))
    calibration_payload = json.loads(output.read_text(encoding="utf-8"))
    assert report_payload["claim_scope"] == "calibration_split_only_not_final_test_result"
    assert report_payload["threshold_source"] == "calibration_only"
    assert report_payload["ranking_unchanged"] == {"alignment": True, "risk": True}
    assert report_payload["labels"]["risk"] == list(RISK_LABELS)
    assert report_payload["labels"]["alignment"] == list(TASK_ALIGNMENT_LABELS)
    assert "status" in report_payload["quality_gates"]
    assert set(report_payload["risk"]) == {
        "before",
        "after",
        "operating_point_at_frozen_threshold",
    }
    assert len(report_payload["alignment"]["after"]["reliability_diagram"]) == 4
    assert calibration_payload["risk"]["temperature"] > 0
    assert report_payload["policy"]["version"] == "1.0.0"
    assert report_payload["quality_gates"]["status"] == "passed"
    assert calibration_payload["metadata"]["status"] == "frozen"
    assert calibration_payload["metadata"]["provenance"] == report_payload["provenance"]


def test_calibration_bundle_rejects_model_artifact_drift(tmp_path):
    logits_path, _ = _write_logits_bundle(tmp_path)
    model_dir = tmp_path / "frozen-model"
    (model_dir / "weights.bin").write_bytes(b"changed frozen model")

    with pytest.raises(ValueError, match="model artifact hash"):
        load_calibration_arrays(logits_path)


def test_calibration_export_authorization_binds_model_and_input(tmp_path):
    input_path = tmp_path / "calibration.jsonl"
    input_path.write_text("synthetic\n", encoding="utf-8")
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "weights.bin").write_bytes(b"weights")
    authorization_path = tmp_path / "export_authorization.json"
    authorization_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "calibration_export_authorized": True,
                "human_verified": True,
                "final_test_lock_preserved": True,
                "approved_by_project_owner": "owner",
                    "approved_at": "2026-08-31T12:00:00+08:00",
                    "model_dir": str(model_dir.resolve()),
                    "model_artifact_sha256": artifact_tree_sha256(model_dir),
                    "model_revision": "fixture-model-revision",
                    "input": str(input_path.resolve()),
                "input_sha256": sha256_file(input_path),
            }
        ),
        encoding="utf-8",
    )

    payload = validate_calibration_export_authorization(
        authorization_path,
        model_dir=model_dir,
        model_artifact_sha256=artifact_tree_sha256(model_dir),
        model_revision="fixture-model-revision",
        input_path=input_path,
        input_sha256=sha256_file(input_path),
    )
    assert payload["calibration_export_authorized"] is True


def test_calibration_load_rejects_unbound_legacy_artifact(tmp_path):
    output = tmp_path / "calibration.json"
    MultiHeadCalibration(TemperatureScaler(), TemperatureScaler()).save(output)

    with pytest.raises(ValueError, match="frozen metadata"):
        MultiHeadCalibration.load(output)


def test_calibration_export_authorization_binds_model_revision(tmp_path):
    input_path = tmp_path / "calibration.jsonl"
    input_path.write_text("synthetic\n", encoding="utf-8")
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "weights.bin").write_bytes(b"weights")
    authorization_path = tmp_path / "export_authorization.json"
    authorization_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "calibration_export_authorized": True,
                "human_verified": True,
                "final_test_lock_preserved": True,
                "approved_by_project_owner": "owner",
                "approved_at": "2026-08-31T12:00:00+08:00",
                "model_dir": str(model_dir.resolve()),
                "model_artifact_sha256": artifact_tree_sha256(model_dir),
                "model_revision": "wrong-revision",
                "input": str(input_path.resolve()),
                "input_sha256": sha256_file(input_path),
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="model_revision"):
        validate_calibration_export_authorization(
            authorization_path,
            model_dir=model_dir,
            model_artifact_sha256=artifact_tree_sha256(model_dir),
            model_revision="fixture-model-revision",
            input_path=input_path,
            input_sha256=sha256_file(input_path),
        )
