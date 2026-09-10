import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from diagnose_toolsafety_audit import (  # noqa: E402
    MARKER,
    definition_diagnosis,
    diagnose,
    parameter_name_findings,
)


def test_identical_repeat_is_distinct_from_conflicting_definition():
    tool = {"name": "read", "parameters": {"properties": {"path": {}}, "required": ["path"]}}
    status, defs = definition_diagnosis(MARKER + json.dumps([tool, tool]))
    assert status == "identical_repeated_definitions" and defs == {"read": tool}
    status, defs = definition_diagnosis(MARKER + json.dumps([tool, tool | {"description": "different"}]))
    assert status == "conflicting_same_name" and defs == {}


def test_parameter_name_screen_does_not_silently_accept_missing_or_unknown_names():
    tool = {"parameters": {"properties": {"path": {}}, "required": ["path"]}}
    assert parameter_name_findings([{"name": "read", "arguments": {"other": "x"}}], {"read": tool}) == {"missing_required_argument", "argument_not_in_declared_properties"}
    assert parameter_name_findings([{"name": "write", "arguments": {}}], {"read": tool}) == {"tool_not_declared"}


def test_malformed_previous_call_cannot_pass_pair_screen():
    tool = {"name": "read", "parameters": {"properties": {"path": {}}, "required": ["path"]}}
    row = {"system": MARKER + json.dumps([tool]), "conversations": [
        {"from": "user", "value": "Read the provided item."},
        {"from": "assistant", "value": '[read(path="unclosed)]'},
        {"from": "tool", "value": '[{"name":"read","result":"ok"}]'},
        {"from": "assistant", "value": '[read(path="next")]'},
    ]}
    report = diagnose([row])
    assert report["position_evidence"][0]["findings"] == ["unresolved_previous_call_result_pair"]
    assert report["rows_passing_name_and_pair_checks_by_definition_status"] == {}
