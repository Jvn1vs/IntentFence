import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_candidate_9_aib import summarize  # noqa: E402


def case(case_id="x"):
    return {"id": case_id, "attack_category": "data_exfiltration", "attacker_intent": "exfiltration",
            "ground_truth": "unsafe", "complexity": "single_turn", "conversation": [
                {"role": "tool_result", "content": "Untrusted fixture"},
                {"role": "assistant", "content": "I will not follow that instruction."}]}


def test_unsafe_case_does_not_invent_action_or_alignment():
    result = summarize([case()])
    assert result["explicit_action_fields"] == []
    assert result["labels_applied"] == 0 and result["training_ready"] is False


def test_action_boundary_and_shared_content():
    a, b = case(), case("y")
    a["conversation"].append({"role": "tool_call", "tool": "mock", "content": "{}"})
    result = summarize([a, b])
    assert result["explicit_action_fields"][0]["after_tool_result"] is False
    assert result["exact_shared_text_groups"]["tool_result"] == [["x", "y"]]


def test_duplicate_ids_rejected():
    with pytest.raises(ValueError, match="Duplicate"):
        summarize([case(), case()])
