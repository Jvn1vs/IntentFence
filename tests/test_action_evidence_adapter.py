import copy

import pytest

from intentfence.action_evidence_adapter import EvidenceOrigin, adapt


def fixture():
    return {"policy": "prepared", "candidate_action": {"tool": "memory.test", "arguments": {}},
            "field_provenance": {"content": {"span": [0, 1]}}, "executed": False,
            "external_side_effects": False}, EvidenceOrigin(source_file="fixture.json", source_file_sha256="a"*64,
                record_index=0, observation_index=0, case_id="fixture", implementation_hashes={"fixture.py": "b"*64})


def test_identity_binds_action_and_implementation_without_promotion():
    observation, origin = fixture()
    before = copy.deepcopy(observation)
    one = adapt(observation, origin)
    assert observation == before
    assert one == adapt(observation, origin)
    observation["candidate_action"]["arguments"]["value"] = "changed"
    assert one["proposed_action"]["arguments"] == {}
    assert adapt(observation, origin)["action_observation_id"] != one["action_observation_id"]
    origin = origin.model_copy(update={"implementation_hashes": {"fixture.py": "c"*64}})
    assert adapt(observation, origin)["action_policy_id"] != one["action_policy_id"]
    assert not one["training_ready"] and one["task_alignment_label"] is None


@pytest.mark.parametrize("field,value", [("executed", True), ("field_provenance", {}),
                                     ("policy", ""), ("human_verified", True), ("split", "train")])
def test_rejects_incomplete_or_promoted_evidence(field, value):
    observation, origin = fixture()
    observation[field] = value
    with pytest.raises(ValueError):
        adapt(observation, origin)
