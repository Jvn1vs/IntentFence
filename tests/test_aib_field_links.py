import pytest

from scripts.verify_aib_field_links import resolve_span, verify_fields


def test_literal_mismatch_and_role_are_not_accepted():
    prefix = [{"role": "tool_result", "content": "text"}]
    o = {"field_provenance": {"content": {"span": {"message": 0, "start": 0, "end": 4}, "role": "tool_result"}},
         "candidate_action": {"tool": "memory.return_result", "arguments": {"content": "text"}}}
    assert verify_fields(prefix, o) == ("exact_literal_arguments", 1)
    o["candidate_action"]["arguments"]["content"] = "other"
    with pytest.raises(ValueError, match="literal"):
        verify_fields(prefix, o)


@pytest.mark.parametrize("span", [{"message": -1, "start": 0, "end": 1},
                                 {"message": 0, "start": 0, "end": 99},
                                 {"message": True, "start": 0, "end": 1}])
def test_outside_prefix_or_range_fails(span):
    with pytest.raises(ValueError):
        resolve_span([{"role": "user", "content": "abc"}], span)
