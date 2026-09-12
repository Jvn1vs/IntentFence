import pytest

from scripts.package_aib_risk_review import content_before_action


def test_latest_result_not_future_action_or_source_label():
    source = {"ground_truth": "unused", "conversation": [
        {"role": "tool_result", "content": "first"},
        {"role": "user", "content": "followup"},
        {"role": "tool_result", "content": "second"},
        {"role": "tool_result", "content": "future"}]}
    assert content_before_action(source, 3) == (2, "second")
    assert content_before_action(source, 2) == (0, "first")


@pytest.mark.parametrize("boundary", [-1, 0, True, 2])
def test_invalid_boundary_fails(boundary):
    with pytest.raises(ValueError):
        content_before_action({"conversation": [{"role": "user", "content": "goal"}]}, boundary)
