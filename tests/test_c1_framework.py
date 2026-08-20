from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from apply_label_audit import apply_audit  # noqa: E402
from summarize_label_audit import summarize  # noqa: E402
from validate_c1_framework import validate  # noqa: E402

from baselines.evaluate_scores import evaluate_frozen_threshold  # noqa: E402
from intentfence.schema import IntentSample  # noqa: E402


def test_c1_framework_contract_is_valid() -> None:
    assert validate() == []


def test_audit_summary_requires_completed_provenance() -> None:
    rows = [
        {
            "sample_id": "one",
            "source": "BIPIA",
            "action_provenance": "missing",
            "risk_label": "benign",
            "audit_status": "correct",
            "new_risk_label": "",
            "new_alignment_label": "",
            "new_severity": "",
            "reviewer": "owner",
            "reviewed_at": "2026-08-20",
        },
        {
            "sample_id": "two",
            "source": "InjecAgent",
            "action_provenance": "benchmark_target",
            "risk_label": "tool_manipulation",
            "audit_status": "incorrect",
            "new_risk_label": "data_exfiltration",
            "new_alignment_label": "1",
            "new_severity": "4",
            "reviewer": "owner",
            "reviewed_at": "2026-08-20",
        },
    ]

    report = summarize(rows, minimum_rows=2)

    assert report["status"] == "passed"
    assert report["status_counts"] == {"correct": 1, "incorrect": 1}
    assert report["risk_corrections"][0]["to"] == "data_exfiltration"


def test_validated_audit_correction_is_applied() -> None:
    sample = IntentSample(
        sample_id="one",
        source="test",
        user_goal="read",
        untrusted_content="external text",
        proposed_action="send()",
        risk_label="tool_manipulation",
        alignment_label=1,
        severity=3,
        template_group="g1",
    )
    rows = [
        {
            "sample_id": "one",
            "source": "test",
            "action_provenance": "source_field",
            "risk_label": "tool_manipulation",
            "audit_status": "incorrect",
            "new_risk_label": "data_exfiltration",
            "new_alignment_label": "1",
            "new_severity": "4",
            "reviewer": "owner",
            "reviewed_at": "2026-08-20",
        }
    ]

    output, report = apply_audit([sample], rows, minimum_rows=1)

    assert output[0].risk_label == "data_exfiltration"
    assert output[0].human_verified is True
    assert output[0].label_provenance == "user_audit_correction"
    assert report["application_counts"] == {"corrected": 1}


def test_audit_summary_rejects_incomplete_review() -> None:
    report = summarize(
        [
            {
                "audit_status": "correct",
                "reviewer": "",
                "reviewed_at": "",
                "source": "BIPIA",
                "action_provenance": "missing",
            }
        ],
        minimum_rows=2,
    )

    assert report["status"] == "failed"
    assert any("reviewer and reviewed_at" in error for error in report["errors"])
    assert any("completed audit rows" in error for error in report["errors"])


def test_baseline_threshold_is_selected_from_calibration_only() -> None:
    calibration = [
        {"attack_label": 0, "attack_score": 0.10},
        {"attack_label": 0, "attack_score": 0.20},
        {"attack_label": 1, "attack_score": 0.80},
        {"attack_label": 1, "attack_score": 0.90},
    ]
    test = [
        {"attack_label": 0, "attack_score": 0.95},
        {"attack_label": 1, "attack_score": 0.70},
    ]

    result = evaluate_frozen_threshold(calibration, test, target_fpr=0.01, minimum_tpr=0.80)

    assert result["threshold_source"] == "calibration_only"
    assert result["calibration"]["fpr"] == 0.0
    assert result["calibration"]["tpr"] == 1.0
    assert result["test"]["fpr"] == 1.0
