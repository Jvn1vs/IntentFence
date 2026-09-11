import copy

import pytest

from scripts.inventory_aib_actions import inspect_record


def test_inventory_accepts_single_and_multi_records_without_promoting_labels():
    observation = {"candidate_action": {"tool": "memory.clarification"},
                   "executed": False, "external_side_effects": False}
    record = {"source_binding": {"case_id": "fixture"}, "human_verified": False,
              "training_ready": False, "observation": observation, "split": None}
    assert inspect_record(record) == ("fixture", [observation])
    multiple = copy.deepcopy(record)
    del multiple["observation"]
    multiple["observations"] = [observation, observation]
    assert len(inspect_record(multiple)[1]) == 2


@pytest.mark.parametrize("field,value", [("risk_label", "benign"), ("human_verified", True),
                                        ("training_ready", True), ("split", "train")])
def test_inventory_rejects_promotion(field, value):
    record = {"case_id": "fixture", "human_verified": False, "training_ready": False,
              "observations": [{"executed": False, "external_side_effects": False}]}
    record[field] = value
    with pytest.raises(ValueError):
        inspect_record(record)
