import csv
import io

import pytest

from scripts.package_aib_alignment_review import FIELDS
from scripts.validate_aib_alignment_return import validate


def encode(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def fixture():
    original = dict.fromkeys(FIELDS, "")
    original.update(review_id="fixture", material_sha256="fixture", user_goal="goal",
                    history_before_action="[]", source_tool_definitions="[]", proposed_action="{}")
    completed = original | {"review_status": "completed", "task_alignment_label_review": "aligned",
                            "action_realism_review": "realistic", "reviewer_id": "fixture-reviewer",
                            "reviewed_at": "2026-09-12T10:00:00+08:00"}
    return original, completed


def test_valid_return_does_not_authenticate_or_apply():
    before, after = fixture()
    result = validate(encode([before]), encode([after]), "fixture-reviewer")
    assert result["form_integrity_verified"]
    assert not result["independence_verified"] and result["labels_applied"] == 0


@pytest.mark.parametrize("field,value", [("user_goal", "changed"), ("reviewer_id", "other"),
    ("reviewed_at", "2026-09-12T10:00:00"), ("review_status", ""),
    ("task_alignment_label_review", "safe"), ("review_status", "unable_to_determine")])
def test_invalid_returns_fail(field, value):
    before, after = fixture()
    after[field] = value
    with pytest.raises(ValueError):
        validate(encode([before]), encode([after]), "fixture-reviewer")


def test_abstention_is_not_ambiguous_and_duplicate_rows_fail():
    before, after = fixture()
    after.update(review_status="unable_to_determine", task_alignment_label_review="", notes="insufficient evidence")
    assert validate(encode([before]), encode([after]), "fixture-reviewer")["alignment_opinions"] == {"abstain": 1}
    with pytest.raises(ValueError, match="duplicate"):
        validate(encode([before]), encode([after, after]), "fixture-reviewer")
