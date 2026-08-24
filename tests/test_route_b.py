from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import yaml

from intentfence.route_b import (
    build_mock_catalog_records,
    precision_table,
    validate_route_b_samples,
    wilson_interval,
)
from intentfence.schema import IntentSample


def _policy() -> dict:
    return {
        "status": "draft_unfrozen_not_training_authorized",
        "risk_labels": [
            "benign",
            "instruction_hijacking",
            "data_exfiltration",
            "privilege_escalation",
            "tool_manipulation",
        ],
        "task_alignment_labels": ["aligned", "unrelated", "ambiguous", "malicious"],
        "action_evidence": {
            "allowed_internal_provenance": ["sandbox_policy_output", "source_field"]
        },
        "sample_size": {"status": "pending_reproducible_precision_or_power_analysis"},
        "readiness": {"formal_training_authorized": False},
    }


def _row(index: int, risk: str, alignment: str, pair: str) -> IntentSample:
    return IntentSample(
        sample_id=f"route-b-{index}",
        source="IntentFenceMock",
        scenario="mock inbox",
        user_goal=f"Process approved item {pair}",
        untrusted_content=f"Synthetic content for {risk} in {pair}",
        proposed_action=f'{{"tool":"mock_write","item":"{pair}","variant":"{alignment}"}}',
        risk_label=risk,
        alignment_label=int(risk != "benign"),
        task_alignment_label=alignment,
        severity=0 if risk == "benign" else 3,
        template_group=f"template-{pair}",
        split="train",
        adapter_profile="route_b_mock_v1",
        action_provenance="sandbox_policy_output",
        action_observation_id=f"trace-{index}",
        action_policy_id="deterministic-mock-policy-v1",
        action_pair_group=pair,
    )


def _valid_rows() -> list[IntentSample]:
    alignments = {
        "benign": ("aligned", "unrelated"),
        "instruction_hijacking": ("aligned", "malicious"),
        "data_exfiltration": ("aligned", "malicious"),
        "privilege_escalation": ("aligned", "ambiguous"),
        "tool_manipulation": ("aligned", "malicious"),
    }
    rows: list[IntentSample] = []
    for risk, pair_alignments in alignments.items():
        pair = f"pair-{risk}"
        for alignment in pair_alignments:
            rows.append(_row(len(rows), risk, alignment, pair))
    return rows


def test_route_b_fixture_passes_structure_but_not_readiness() -> None:
    report = validate_route_b_samples(_valid_rows(), _policy())
    assert report["errors"] == []
    assert report["status"] == "structure_passed_readiness_blocked"
    assert "formal_training_authorized is false" in report["readiness_blockers"]
    assert report["summary"]["action_pair_groups"] == 5


def test_route_b_rejects_locked_test_source_in_training() -> None:
    rows = _valid_rows()
    rows[0] = rows[0].model_copy(update={"source": "InjecAgent"})
    report = validate_route_b_samples(rows, _policy())
    assert any("may only use test_b" in error for error in report["errors"])


def test_route_b_rejects_risk_alignment_confounding() -> None:
    rows = [
        row.model_copy(
            update={
                "task_alignment_label": (
                    "aligned" if row.risk_label == "benign" else "malicious"
                )
            }
        )
        for row in _valid_rows()
    ]
    report = validate_route_b_samples(rows, _policy())
    assert any("no non-benign/aligned counterexample" in error for error in report["errors"])
    assert any("no benign/non-aligned counterexample" in error for error in report["errors"])


def test_route_b_rejects_template_leakage_across_internal_roles() -> None:
    rows = _valid_rows()
    leaked = deepcopy(rows[0].model_dump(mode="python"))
    leaked.update(
        sample_id="leaked-validation-row",
        split="validation",
        action_observation_id="trace-leaked",
        proposed_action='{"tool":"mock_read","item":"different"}',
        action_pair_group="validation-pair",
    )
    companion = deepcopy(leaked)
    companion.update(
        sample_id="leaked-validation-companion",
        action_observation_id="trace-leaked-2",
        proposed_action='{"tool":"mock_write","item":"different"}',
        task_alignment_label="ambiguous",
    )
    rows.extend([IntentSample(**leaked), IntentSample(**companion)])
    report = validate_route_b_samples(rows, _policy())
    assert any("template_group crosses internal roles" in error for error in report["errors"])


def test_wilson_precision_planner_is_deterministic() -> None:
    lower, upper = wilson_interval(1, 100)
    assert 0 < lower < 0.01 < upper < 0.1
    table = precision_table([100, 1000], target_rate=0.01)
    assert table[0]["one_event_resolution"] == 0.01
    assert table[1]["one_event_resolution"] == 0.001
    assert table[1]["wilson_95_half_width"] < table[0]["wilson_95_half_width"]


def test_mock_catalog_captures_candidates_without_execution() -> None:
    fixture = Path(__file__).parent / "fixtures" / "route_b_mock_catalog.yaml"
    catalog = yaml.safe_load(fixture.read_text(encoding="utf-8"))
    records, traces = build_mock_catalog_records(catalog)
    assert len(records) == len(traces) == 10
    assert all(trace["executed"] is False for trace in traces)
    assert all(trace["external_side_effects"] is False for trace in traces)
    report = validate_route_b_samples(records, _policy())
    assert report["errors"] == []
