import pytest

from scripts.compare_aib_alignment_reviews import compare


def row(key, label, status="completed"):
    return {"review_id": key, "material_sha256": key, "review_status": status,
            "task_alignment_label_review": label, "action_realism_review": "realistic", "notes": "fixture"}


def test_abstention_excluded_and_order_independent():
    a = [row("1", "aligned"), row("2", "malicious"), row("3", "", "unable_to_determine")]
    b = [row("3", "aligned"), row("2", "malicious"), row("1", "aligned")]
    result = compare(a, b)
    assert result["both_completed"] == 2
    assert result["cohen_kappa_on_both_completed"] == 1
    assert len(result["disagreements"]) == 1
    assert not result["full_protocol_acceptance"]


def test_degenerate_kappa_is_unavailable_not_perfect():
    a = [row("1", "aligned")]
    assert compare(a, a)["cohen_kappa_on_both_completed"] is None
    with pytest.raises(ValueError):
        compare(a, [row("2", "aligned")])
