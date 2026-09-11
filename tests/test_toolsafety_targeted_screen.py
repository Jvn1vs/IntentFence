from scripts.screen_toolsafety_targeted import prefix_texts, string_leaves


def test_nested_text_without_keys_or_numbers():
    assert string_leaves({"hidden_key": ["body", 8, None, {"x": "nested"}]}) == ["body", "nested"]


def test_only_pre_action_user_and_tool_text():
    row = {"user_goal": "goal", "proposed_action": "excluded future action",
           "history_before_action": [
               {"from": "user", "value": "goal"},
               {"from": "assistant", "value": "excluded assistant"},
               {"from": "tool", "value": '{"result": {"text": "embedded passage"}}'},
               {"from": "tool", "value": "unparsed plain text"}]}
    values = prefix_texts(row)
    assert "embedded passage" in values
    assert "unparsed plain text" in values
    assert not any("excluded" in v for v in values)
    assert values.count("goal") == 1
