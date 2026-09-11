import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from aggregate_aib_scenarios import aggregate  # noqa: E402


def notes(risk="data_exfiltration"):
    return {"x": {"risk": risk, "carrier": "document", "family": "external_transfer",
                  "goal": "summarize", "boundary": "no transfer", "action_gap": "no observed call", "reason": "external recipient"}}


def run(value):
    return aggregate([{"id": "x"}], {"a": json.dumps(value).encode()}, {"a": [0, 0]})


def test_review_does_not_become_action_or_training_label():
    rows, report = run(notes())
    assert rows[0]["risk_label"] is None and rows[0]["proposed_action"] is None
    assert report["provisional_risk_counts"] == {"data_exfiltration": 1}
    assert report["family_isolation_cleared"] is False


def test_abstention_preserved():
    assert run(notes(None))[1]["provisional_risk_counts"] == {"unresolved": 1}


@pytest.mark.parametrize("value", [{}, {"wrong": notes()["x"]}, notes("unsafe")])
def test_incomplete_or_invalid_reviews_rejected(value):
    with pytest.raises(ValueError):
        run(value)


def test_duplicate_json_key_rejected():
    with pytest.raises(ValueError, match="Duplicate JSON"):
        aggregate([{"id": "x"}], {"a": b'{"x":{},"x":{}}'}, {"a": [0, 0]})
