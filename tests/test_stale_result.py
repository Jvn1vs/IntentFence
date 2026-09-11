import pytest

from intentfence.stale_result import StaleResultInput, select_scoped_results


def fixture():
    return {"prefix": [{"role": "user", "content": "Total?"},
                       {"role": "tool_result", "content": "total: 23"},
                       {"role": "user", "content": "Urgent subset?"},
                       {"role": "tool_result", "content": "urgent: 4"}],
            "previous": {"query": {"message": 0, "start": 0, "end": 6},
                         "result": {"message": 1, "start": 0, "end": 9},
                         "value": {"message": 1, "start": 7, "end": 9}},
            "latest": {"query": {"message": 2, "start": 0, "end": 14},
                       "result": {"message": 3, "start": 0, "end": 9},
                       "value": {"message": 3, "start": 8, "end": 9}}}


def test_distinct_counts_preserve_different_query_scopes():
    result = select_scoped_results(StaleResultInput.model_validate(fixture()))
    assert [r["candidate_action"]["arguments"]["content"] for r in result] == ["4", "23"]
    assert result[0]["query_scope"] != result[1]["query_scope"]
    assert all(not r["executed"] for r in result)


@pytest.mark.parametrize("change", ["future", "wrong_query", "outside_result", "non_numeric"])
def test_scope_and_literal_errors_rejected(change):
    raw = fixture()
    if change == "future":
        raw["prefix"].append({"role": "assistant", "content": "future"})
    elif change == "wrong_query":
        raw["latest"]["query"]["message"] = 0
    elif change == "outside_result":
        raw["latest"]["value"]["message"] = 1
    else:
        raw["latest"]["value"]["start"] = 0
    with pytest.raises(ValueError):
        StaleResultInput.model_validate(raw)
