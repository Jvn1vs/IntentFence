import hashlib
import json

import pytest

from intentfence.aib_communication_pilot import CommunicationCase, bind_communication


def fixture():
    row = {"id": "fixture-note", "system_prompt": "Fixture system.", "tools_available": [],
           "conversation": [{"role": "assistant", "content": "Prior summary."},
                            {"role": "user", "content": "Save that as note-title."},
                            {"role": "tool_call", "tool": "save", "content": "future parameters"}]}
    blob = json.dumps(row).encode()
    user = {"message": 2, "start": 0, "end": 24}
    raw = {"source": {"case_id": row["id"], "revision": "fixture-v1", "file_sha256": "0" * 64,
                      "row_sha256": hashlib.sha256(blob).hexdigest()},
           "conversation_boundary": 2,
           "scenario": {"case_id": row["id"], "prefix": [
               {"role": "system", "content": row["system_prompt"]}, *row["conversation"][:2]],
               "decision_boundary": 3, "current_user": 2,
               "goal": {"operation": "note",
                        "title": {"candidates": [{"message": 2, "start": 13, "end": 23}],
                                  "current_user_authorization": user},
                        "body": {"candidates": [{"message": 1, "start": 0, "end": 14}],
                                 "current_user_authorization": user}},
               "preparation_author": "Codex/AI", "preparation_reason": "Fixture explicit reference."},
           "reviewer": "Codex/AI", "review": "Fixture review."}
    # Bind the actual string lengths, not hypothetical source offsets.
    user["end"] = len(row["conversation"][1]["content"])
    raw["scenario"]["goal"]["title"]["candidates"][0]["end"] = user["end"] - 1
    return blob, raw


def test_note_source_projection_and_no_labels():
    blob, raw = fixture()
    result = bind_communication(blob, CommunicationCase.model_validate(raw))
    assert result["observation"]["candidate_action"]["arguments"] == {
        "title": "note-title", "body": "Prior summary."}
    assert result["status"] == "proposal_quarantined"
    assert result["task_alignment_label"] is None and result["split"] is None
    assert result["observation"]["runtime"] == "prepared_communication_source_pilot"
    assert result == bind_communication(blob, CommunicationCase.model_validate(raw))


@pytest.mark.parametrize("mutation", ["hash", "prefix", "boundary", "identity"])
def test_source_binding_rejects_changes(mutation):
    blob, raw = fixture()
    if mutation == "hash":
        blob += b" "
    elif mutation == "prefix":
        raw["scenario"]["prefix"][0]["content"] += " changed"
    elif mutation == "boundary":
        raw["conversation_boundary"] = 3
    else:
        raw["source"]["case_id"] = "wrong"
    with pytest.raises(ValueError):
        bind_communication(blob, CommunicationCase.model_validate(raw))


def test_future_call_changes_binding_but_not_selected_body():
    blob, raw = fixture()
    before = bind_communication(blob, CommunicationCase.model_validate(raw))
    row = json.loads(blob)
    row["conversation"][-1]["content"] = "different future rewritten summary"
    row["ground_truth"] = "arbitrary source label"
    blob = json.dumps(row).encode()
    raw["source"]["row_sha256"] = hashlib.sha256(blob).hexdigest()
    after = bind_communication(blob, CommunicationCase.model_validate(raw))
    assert before["observation"] == after["observation"]
    assert before["bound_observation_id"] != after["bound_observation_id"]


def test_missing_body_is_not_a_successful_note_proposal():
    blob, raw = fixture()
    raw["scenario"]["goal"]["body"]["candidates"] = []
    result = bind_communication(blob, CommunicationCase.model_validate(raw))
    assert result["status"] == "missing_fields_quarantined"
    assert result["observation"]["candidate_action"] == {
        "tool": "memory.clarification", "arguments": {"issues": ["missing:body"]}}
