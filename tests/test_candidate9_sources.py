from __future__ import annotations

import pytest

from intentfence.candidate9_sources import dolly_backgrounds


def row(**changes: str) -> dict[str, str]:
    return (
        dict(
            instruction="Find the launch year.",
            context="The project launched in 2004.",
            response="2004",
            category="closed_qa",
        )
        | changes
    )


def test_selects_grounded_tasks_and_retains_provenance() -> None:
    converted, excluded = dolly_backgrounds(
        [row(), row(category="summarization"), row(category="information_extraction")]
    )
    assert len(converted) == 3 and excluded == {}
    assert converted[0]["goal"] == row()["instruction"]
    assert converted[0]["content"] == row()["context"]
    assert converted[0]["source"] == "DatabricksDolly15k"
    assert "CC-BY-SA-3.0" in converted[0]["attribution"]
    assert not (
        {"proposed_action", "risk_label", "task_alignment_label", "human_verified"}
        & converted[0].keys()
    )


def test_does_not_fabricate_context_from_response() -> None:
    converted, excluded = dolly_backgrounds(
        [row(context=" "), row(category="open_qa"), row(instruction="")]
    )
    assert converted == []
    assert excluded == {
        "missing_reference_context": 1,
        "category_not_selected": 1,
        "missing_instruction": 1,
    }


def test_invalid_record_fails_instead_of_silently_skipping() -> None:
    with pytest.raises(ValueError, match="response"):
        dolly_backgrounds([{"instruction": "q", "context": "c", "category": "closed_qa"}])
