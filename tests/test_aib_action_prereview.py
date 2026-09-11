import hashlib
import json

import pytest

from scripts.verify_aib_action_prereview import verify


def fixture(tmp_path):
    action = {"tool": "memory.example", "arguments": {}}
    raw = json.dumps({"case_id": "fixture", "observations": [{"candidate_action": action}]}).encode()
    (tmp_path / "actions.jsonl").write_bytes(raw)
    sha = hashlib.sha256(raw).hexdigest()
    return {"input_receipts": [{"path": "actions.jsonl", "sha256": sha}],
            "reviews": [{"key": "fixture:0", "source_file": "actions.jsonl", "source_file_sha256": sha,
                         "action_sha256": hashlib.sha256(json.dumps(action, sort_keys=True,
                             separators=(",", ":")).encode()).hexdigest(),
                         "blind": False, "independent_of_preparation": False, "human_verified": False,
                         "applied_to_training": False, "reviewer": "Codex/AI", "alignment_opinion": None,
                         "review_status": "unable_to_determine", "reason": "Fixture abstention.",
                         "action_realism_opinion": "ambiguous"}],
            "human_verified": False, "training_ready": False}


def test_abstention_is_not_ambiguous_label(tmp_path):
    assert verify(fixture(tmp_path), tmp_path)["alignment_opinions"] == {"abstain": 1}


@pytest.mark.parametrize("error", ["missing", "duplicate", "promoted", "wrong_action", "false_independence"])
def test_invalid_reviews_rejected(tmp_path, error):
    data = fixture(tmp_path)
    if error == "missing":
        data["reviews"] = []
    elif error == "duplicate":
        data["reviews"] *= 2
    elif error == "promoted":
        data["reviews"][0]["applied_to_training"] = True
    elif error == "wrong_action":
        data["reviews"][0]["action_sha256"] = "0" * 64
    else:
        data["reviews"][0]["independent_of_preparation"] = True
    with pytest.raises(ValueError):
        verify(data, tmp_path)
