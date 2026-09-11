import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_toolsafety_prefix_review import make_prefix  # noqa: E402
from verify_toolsafety_prefix_review import validate_prefix, validate_reviews  # noqa: E402


def source_row():
    return {"system": "fixture tool definitions", "conversations": [
        {"from": "user", "value": "Read the report"},
        {"from": "assistant", "value": '[read(id="first")]'},
        {"from": "tool", "value": "first result"},
        {"from": "assistant", "value": '[read(id="second")]'},
        {"from": "tool", "value": "FUTURE OUTCOME MUST NOT LEAK"},
        {"from": "assistant", "value": "FUTURE SUMMARY MUST NOT LEAK"},
    ]}


def test_future_outcomes_cannot_change_prefix_or_its_hash():
    source = source_row()
    prefix = make_prefix(source, 0, 2)
    altered = copy.deepcopy(source)
    altered["conversations"][4]["value"] = "different future outcome"
    assert prefix == make_prefix(altered, 0, 2)
    assert prefix["history_before_action"] == source["conversations"][:3]
    assert prefix["proposed_action"] == '[read(id="second")]'
    validate_prefix(prefix, source)
    prefix["history_before_action"].append(source["conversations"][4])
    with pytest.raises(ValueError, match="Source replay mismatch"):
        validate_prefix(prefix, source)


@pytest.mark.parametrize("field,value", [("human_verified", True), ("split", "train"), ("risk_review", "benign"), ("proposed_action", "changed")])
def test_verifier_rejects_label_promotion_or_source_changes(field, value):
    source = source_row()
    prefix = make_prefix(source, 0, 2)
    prefix[field] = value
    with pytest.raises(ValueError, match="Source replay mismatch"):
        validate_prefix(prefix, source)


def review(prefix):
    return {"review_id": prefix["review_id"], "prefix_sha256": prefix["prefix_sha256"],
            "reviewer": "AI/Codex", "human_verified": False, "training_ready": False,
            "semantic_note": "Author inspected this fixture.", "risk_label": None,
            "alignment_label": None, "full_context_pre_review": None}


def test_review_membership_and_provenance_fail_closed():
    prefix = make_prefix(source_row(), 0, 2)
    row = review(prefix)
    assert validate_reviews([prefix], [row])["ai_full_context_pre_review_rows"] == 0
    for rows in [[], [row, row], [row | {"review_id": "foreign"}], [row | {"human_verified": True}],
                 [row | {"risk_label": "benign"}], [row | {"prefix_sha256": "bad"}]]:
        with pytest.raises(ValueError):
            validate_reviews([prefix], rows)


def test_risk_and_alignment_are_independent_and_nullable():
    prefix = make_prefix(source_row(), 0, 2)
    row = review(prefix) | {"full_context_pre_review": {"risk": "benign", "alignment": "unrelated", "reason": "Wrong target without attack."}}
    assert validate_reviews([prefix], [row])["ai_full_context_pre_review_rows"] == 1
    row["full_context_pre_review"]["alignment"] = "benign"
    with pytest.raises(ValueError):
        validate_reviews([prefix], [row])
