import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from aggregate_toolsafety_full_reviews import merge_notes  # noqa: E402


def payload(index="0", **changes):
    return json.dumps({index: {"risk": "benign", "alignment": "unrelated", "reason": "Wrong target without attack."} | changes}).encode()


def test_merge_keeps_independent_judgments_out_of_training_fields():
    rows, report = merge_notes([{"review_id": "a", "prefix_sha256": "hash"}], [("reviewer", payload())])
    assert rows[0]["provisional_review"]["alignment"] == "unrelated"
    assert rows[0]["risk_label"] is None and rows[0]["alignment_label"] is None
    assert rows[0]["human_verified"] is False and rows[0]["training_ready"] is False
    assert report["remaining"] == 0 and report["independent_double_review"] is False


def test_missing_rows_and_abstention_are_not_filled_in():
    rows, report = merge_notes([{"review_id": "a", "prefix_sha256": "h"}, {"review_id": "b", "prefix_sha256": "h2"}], [("reviewer", payload(risk=None, alignment="ambiguous"))])
    assert report["remaining"] == 1 and report["risk_counts"] == {"unresolved": 1}
    assert len(rows) == 1


@pytest.mark.parametrize("bad", [payload(index="-1"), payload(index="1"), payload(index="00"), payload(alignment="safe"), payload(reason=""), payload(human_verified=True)])
def test_invalid_membership_or_provenance_rejected(bad):
    with pytest.raises(ValueError):
        merge_notes([{"review_id": "a", "prefix_sha256": "h"}], [("reviewer", bad)])


def test_overlap_is_rejected_instead_of_arbitrarily_overwriting():
    with pytest.raises(ValueError, match="Duplicate"):
        merge_notes([{"review_id": "a", "prefix_sha256": "h"}], [("a", payload()), ("b", payload(alignment="aligned"))])
