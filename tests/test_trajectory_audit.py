from __future__ import annotations

import pytest

from intentfence.trajectory_audit import declared_tools, literal_tool_calls, result_names


def test_parses_literal_calls_without_executing_them():
    assert literal_tool_calls('[read_file(path="/example"), lookup(keys=[1, 2])]') == [
        {"name": "read_file", "arguments": {"path": "/example"}},
        {"name": "lookup", "arguments": {"keys": [1, 2]}},
    ]


@pytest.mark.parametrize("text", [
    '[call(value=__import__("os").system("echo forbidden"))]',
    '[os.system(command="forbidden")]',
    '[call(**parameters)]', '[call("positional")]', '[call(x=1, x=2)]',
    'I cannot perform that action.', '[]', '[call(value=true)]',
])
def test_unsupported_text_is_not_treated_as_a_parsed_action(text):
    assert literal_tool_calls(text) is None


def test_result_pairing_requires_named_results():
    assert result_names('[{"name":"lookup","result":{"value":1}}]') == ["lookup"]
    assert result_names('[{"name":"lookup"}]') is None
    assert result_names('{"name":"lookup","result":1}') is None
    assert result_names('not JSON') is None


def test_tool_definitions_allow_trailing_format_guidance_but_not_duplicate_names():
    prefix = 'Here is a list of functions in JSON format that you can invoke:\n'
    item = '{"name":"lookup","parameters":{"type":"object"}}'
    assert declared_tools(prefix + '[' + item + ']\nFormat guidance') == {
        "lookup": {"name": "lookup", "parameters": {"type": "object"}}
    }
    assert declared_tools(prefix + '[' + item + ',' + item + ']') is None
    assert declared_tools('no definition marker') is None
