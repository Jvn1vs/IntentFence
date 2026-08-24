from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from baselines.aggregate_results import aggregate, render_markdown
from baselines.evaluate_scores import main as evaluate_scores_main


def _prediction(
    sample_id: str,
    split: str,
    label: int,
    score: float,
    *,
    backend: str = "rules",
    revision: str = "repository_rules",
) -> dict[str, object]:
    return {
        "sample_id": sample_id,
        "split": split,
        "source": "synthetic",
        "attack_label": label,
        "risk_label": "benign" if label == 0 else "instruction_hijacking",
        "attack_score": score,
        "backend": backend,
        "revision": revision,
    }


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_score_evaluation_records_identity_hashes_and_protocol(
    tmp_path: Path, monkeypatch
) -> None:
    calibration = tmp_path / "calibration.jsonl"
    test = tmp_path / "test_a.jsonl"
    output = tmp_path / "result.json"
    _write_jsonl(
        calibration,
        [
            _prediction("cal_b", "calibration", 0, 0.1),
            _prediction("cal_a", "calibration", 1, 0.9),
        ],
    )
    _write_jsonl(
        test,
        [
            _prediction("test_b", "test_a", 0, 0.2),
            _prediction("test_a", "test_a", 1, 0.8),
        ],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_scores.py",
            "--calibration",
            str(calibration),
            "--test",
            str(test),
            "--output",
            str(output),
            "--default-threshold",
            "0.5",
        ],
    )

    evaluate_scores_main()

    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["threshold_source"] == "calibration_only"
    assert result["protocol_version"] == "1.0.0"
    assert result["backend"] == "rules"
    assert result["revision"] == "repository_rules"
    assert result["test_split"] == "test_a"
    assert len(result["calibration_predictions_sha256"]) == 64
    assert result["test_diagnostics"]["status"] == "available"
    assert result["default_threshold_test"]["fpr"] == 0.0


def test_score_evaluation_rejects_backend_drift(tmp_path: Path, monkeypatch) -> None:
    calibration = tmp_path / "calibration.jsonl"
    test = tmp_path / "test_a.jsonl"
    _write_jsonl(
        calibration,
        [
            _prediction("cal_b", "calibration", 0, 0.1),
            _prediction("cal_a", "calibration", 1, 0.9),
        ],
    )
    _write_jsonl(
        test,
        [
            _prediction("test_b", "test_a", 0, 0.2, backend="tfidf"),
            _prediction("test_a", "test_a", 1, 0.8, backend="tfidf"),
        ],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_scores.py",
            "--calibration",
            str(calibration),
            "--test",
            str(test),
            "--output",
            str(tmp_path / "unused.json"),
        ],
    )

    with pytest.raises(ValueError, match="same backend"):
        evaluate_scores_main()


def test_baseline_aggregator_enforces_expected_matrix(tmp_path: Path) -> None:
    result_path = tmp_path / "rules_test_a.json"
    payload = {
        "threshold_source": "calibration_only",
        "backend": "rules",
        "revision": "repository_rules",
        "test_split": "test_a",
        "threshold": 0.5,
        "test": {"fpr": 0.0, "tpr": 1.0, "precision": 1.0, "fp": 0, "fn": 0},
        "operational_failure": False,
    }
    result_path.write_text(json.dumps(payload), encoding="utf-8")

    report = aggregate(
        [("rules", result_path, payload)],
        expected_baselines={"rules", "tfidf_word"},
        expected_tests={"test_a"},
    )

    assert report["status"] == "failed"
    assert any("tfidf_word" in error for error in report["errors"])
    assert "Frozen baseline result table" in render_markdown(report)
