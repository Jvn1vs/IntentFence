import pytest

from scripts.build_aib_preparation_register import assemble


def opinion(index, alignment, realism="realistic"):
    return {"key": f"case:{index}", "alignment_opinion": alignment,
            "action_realism_opinion": realism, "source_file": "fixture", "action_sha256": "fixture"}


def test_abstention_and_unrealistic_do_not_complete_pair():
    result = assemble([opinion(0, "aligned"), opinion(1, None),
                       opinion(2, "malicious", "unrealistic")],
                      {"case": {"risk": "benign"}}, [["case", "linked_unselected"]])
    assert result["summary"]["cases_with_different_nonabstained_realistic_opinions"] == []
    assert result["entries"][0]["constraint_group_members"] == ["case", "linked_unselected"]
    assert all(r["alignment_label"] is None and not r["training_ready"] for r in result["entries"])


def test_pair_is_only_opinion_coverage():
    result = assemble([opinion(0, "aligned"), opinion(1, "malicious")],
                      {"case": {"risk": "tool_manipulation"}}, [["case"]])
    assert result["summary"]["cases_with_different_nonabstained_realistic_opinions"] == ["case"]
    assert result["summary"]["training_ready"] is False


def test_missing_and_duplicate_membership_fail():
    with pytest.raises(ValueError, match="missing"):
        assemble([opinion(0, "aligned")], {"case": {"risk": "benign"}}, [["other"]])
    with pytest.raises(ValueError, match="duplicate constraint"):
        assemble([], {}, [["case"], ["case"]])
