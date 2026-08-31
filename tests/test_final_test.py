from __future__ import annotations

import json
from pathlib import Path

import pytest

from intentfence.final_test import (
    FINAL_TEST_SPLITS,
    artifact_tree_sha256,
    claim_final_test_ledger,
    complete_final_test_ledger,
    validate_final_test_authorization,
)
from intentfence.run_manifest import sha256_file


def _final_test_fixture(tmp_path: Path) -> dict:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "weights.bin").write_bytes(b"frozen fixture weights")
    calibration_path = tmp_path / "calibration.json"
    calibration_path.write_text('{"version":"1"}\n', encoding="utf-8")
    calibration_report_path = tmp_path / "calibration_report.json"
    calibration_report_path.write_text(
        '{"frozen_attack_threshold":0.5,"threshold_source":"calibration_only"}\n',
        encoding="utf-8",
    )
    test_inputs = {}
    for split in FINAL_TEST_SPLITS:
        path = tmp_path / f"{split}.jsonl"
        path.write_text(
            json.dumps(
                {
                    "sample_id": f"{split}-sample",
                    "source": "fixture",
                    "untrusted_content": split,
                    "risk_label": "benign",
                    "alignment_label": 0,
                    "template_group": f"{split}-group",
                    "split": split,
                    "action_provenance": "missing",
                    "adapter_missing_action": True,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        test_inputs[split] = path
    authorization_path = tmp_path / "authorization.json"
    payload = {
        "formal_final_test_authorized": True,
        "human_verified": True,
        "final_test_lock_preserved": True,
        "protocol_version": "1.0.0",
        "test_splits": list(FINAL_TEST_SPLITS),
        "frozen_attack_threshold": 0.5,
        "approved_by_project_owner": "fixture-owner",
        "approved_at": "2026-08-31T12:00:00+08:00",
        "model_dir": str(model_dir.resolve()),
        "model_artifact_sha256": artifact_tree_sha256(model_dir),
        "calibration_path": str(calibration_path.resolve()),
        "calibration_sha256": sha256_file(calibration_path),
        "calibration_report_path": str(calibration_report_path.resolve()),
        "calibration_report_sha256": sha256_file(calibration_report_path),
        "test_input_paths": {
            split: str(path.resolve()) for split, path in test_inputs.items()
        },
        "test_input_sha256": {split: sha256_file(path) for split, path in test_inputs.items()},
    }
    authorization_path.write_text(json.dumps(payload), encoding="utf-8")
    return {
        "authorization": authorization_path,
        "registry": Path(__file__).resolve().parents[1] / "configs" / "experiment_registry.yaml",
        "model": model_dir,
        "calibration": calibration_path,
        "calibration_report": calibration_report_path,
        "test_inputs": test_inputs,
    }


def test_final_test_authorization_binds_all_frozen_inputs(tmp_path):
    fixture = _final_test_fixture(tmp_path)
    payload = validate_final_test_authorization(
        fixture["authorization"],
        registry_path=fixture["registry"],
        model_dir=fixture["model"],
        calibration_path=fixture["calibration"],
        calibration_report_path=fixture["calibration_report"],
        test_inputs=fixture["test_inputs"],
        attack_threshold=0.5,
    )

    assert payload["test_splits"] == list(FINAL_TEST_SPLITS)
    mutated_path = fixture["test_inputs"]["test_b"]
    mutated_payload = json.loads(mutated_path.read_text(encoding="utf-8"))
    mutated_payload["untrusted_content"] = "mutated"
    mutated_path.write_text(json.dumps(mutated_payload) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="test_input_sha256"):
        validate_final_test_authorization(
            fixture["authorization"],
            registry_path=fixture["registry"],
            model_dir=fixture["model"],
            calibration_path=fixture["calibration"],
            calibration_report_path=fixture["calibration_report"],
            test_inputs=fixture["test_inputs"],
            attack_threshold=0.5,
        )


def test_final_test_ledger_is_exclusive_and_completes_once(tmp_path):
    fixture = _final_test_fixture(tmp_path)
    ledger_path = tmp_path / "final_test_ledger.json"
    output_dir = tmp_path / "final_results"
    claimed = claim_final_test_ledger(
        ledger_path,
        authorization_path=fixture["authorization"],
        registry_path=fixture["registry"],
        model_dir=fixture["model"],
        calibration_path=fixture["calibration"],
        calibration_report_path=fixture["calibration_report"],
        test_inputs=fixture["test_inputs"],
        attack_threshold=0.5,
        run_id="fixture-run",
        output_dir=output_dir,
    )

    assert claimed["status"] == "claimed"
    with pytest.raises(FileExistsError, match="second formal matrix"):
        claim_final_test_ledger(
            ledger_path,
            authorization_path=fixture["authorization"],
            registry_path=fixture["registry"],
            model_dir=fixture["model"],
            calibration_path=fixture["calibration"],
            calibration_report_path=fixture["calibration_report"],
            test_inputs=fixture["test_inputs"],
            attack_threshold=0.5,
            run_id="another-run",
            output_dir=tmp_path / "another-results",
        )

    result_paths = {}
    for split in FINAL_TEST_SPLITS:
        result_dir = output_dir / split
        result_dir.mkdir(parents=True)
        (result_dir / "metrics.json").write_text("{}\n", encoding="utf-8")
        result_paths[split] = result_dir
    completed = complete_final_test_ledger(
        ledger_path,
        run_id="fixture-run",
        result_paths=result_paths,
    )

    assert completed["status"] == "completed"
    with pytest.raises(ValueError, match="claimed run"):
        complete_final_test_ledger(
            ledger_path,
            run_id="fixture-run",
            result_paths=result_paths,
        )
