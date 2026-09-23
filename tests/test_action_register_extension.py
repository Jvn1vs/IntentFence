"""Historical evidence remains immutable when a new offline pair is registered."""

from __future__ import annotations

from copy import deepcopy

import pytest

from intentfence.action_register_extension import extend_register


def fixture() -> tuple[dict, dict]:
    base = {
        "entries": [{
            "key": "OLD:0", "action_observation_id": "derived-old",
            "risk_label": None, "task_alignment_label": None, "split": None,
            "human_verified": False, "training_ready": False,
        }],
        "observations": 1,
        "input_hashes": {"old.json": "a" * 64},
        "training_ready": False,
        "route_b_admission_verified": False,
    }
    record = {
        "source_binding": {"case_id": "NEW"},
        "risk_label": None, "task_alignment_labels": None, "split": None,
        "human_verified": False, "training_ready": False,
        "observations": [
            {
                "policy": "goal_bounded", "prefix_sha256": "b" * 64,
                "candidate_action": {"tool": "memory.return_result_proposal",
                                     "arguments": {"content": "mock result"}},
                "field_provenance": {"content": {"span": {"message": 2, "start": 0,
                                                            "end": 11}}},
                "executed": False, "external_side_effects": False,
                "action_provenance": "sandbox_policy_output", "model_generated": False,
            },
            {
                "policy": "content_following", "prefix_sha256": "b" * 64,
                "candidate_action": {"tool": "memory.file_proposal",
                                     "arguments": {"path": "mock.txt", "content": "mock"}},
                "field_provenance": {"path": {"span": {"message": 2, "start": 12,
                                                       "end": 20}}},
                "executed": False, "external_side_effects": False,
                "action_provenance": "sandbox_policy_output", "model_generated": False,
            },
        ],
    }
    return base, record


def add(base: dict, record: dict) -> dict:
    return extend_register(
        base, record, source_file="data/interim/new/record.jsonl",
        source_sha256="c" * 64,
        implementation_hashes={"src/intentfence/mock.py": "d" * 64},
    )


def test_appends_pair_without_mutating_historical_register() -> None:
    base, record = fixture()
    original = deepcopy(base)
    result = add(base, record)
    assert base == original
    assert result["entries"][0] == original["entries"][0]
    assert [e["key"] for e in result["entries"]] == ["OLD:0", "NEW:0", "NEW:1"]
    assert len({e["action_observation_id"] for e in result["entries"]}) == 3
    assert result["observations"] == 3
    assert all(e["human_verified"] is False and e["training_ready"] is False
               for e in result["entries"])
    assert result["training_ready"] is False


def test_rejects_applied_labels_and_duplicate_keys() -> None:
    base, record = fixture()
    base["entries"][0]["risk_label"] = "benign"
    with pytest.raises(ValueError, match="applied label"):
        add(base, record)
    base, record = fixture()
    base["entries"][0]["key"] = "NEW:0"
    with pytest.raises(ValueError, match="duplicate observation key"):
        add(base, record)
    base, record = fixture()
    record["task_alignment_labels"] = ["aligned", "malicious"]
    with pytest.raises(ValueError, match="applied label"):
        add(base, record)


def test_rejects_noncontrasts_and_executed_actions() -> None:
    base, record = fixture()
    record["observations"][1]["prefix_sha256"] = "e" * 64
    with pytest.raises(ValueError, match="same-prefix"):
        add(base, record)
    base, record = fixture()
    record["observations"][0]["prefix_sha256"] = None
    record["observations"][1]["prefix_sha256"] = None
    with pytest.raises(ValueError, match="same-prefix"):
        add(base, record)
    base, record = fixture()
    record["observations"][1]["executed"] = True
    with pytest.raises(ValueError, match="nonexecuted"):
        add(base, record)
    base, record = fixture()
    record["observations"][1]["model_generated"] = True
    with pytest.raises(ValueError, match="honest offline provenance"):
        add(base, record)
