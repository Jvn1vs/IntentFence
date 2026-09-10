"""Explain ToolSafety structural exclusions; never convert or repair source records."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from collections import Counter
from pathlib import Path

from intentfence.trajectory_audit import literal_tool_calls, result_names

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = "e623a0e72b2faf5270876462dc8a3197967c533b00755a80050187db34bcbd72"
MARKER = "Here is a list of functions in JSON format that you can invoke:"


def definition_diagnosis(system: str) -> tuple[str, dict]:
    if system.count(MARKER) != 1:
        return "missing_or_ambiguous_marker", {}
    try:
        items, _ = json.JSONDecoder().raw_decode(system.split(MARKER, 1)[1].lstrip())
    except (ValueError, RecursionError):
        return "invalid_json", {}
    if not isinstance(items, list) or not items:
        return "not_nonempty_list", {}
    if not all(isinstance(item, dict) for item in items):
        return "non_object_member", {}
    definitions = {}
    repeats = False
    for item in items:
        name = item.get("name")
        if not isinstance(name, str) or not name or not isinstance(item.get("parameters"), dict):
            return "invalid_definition", {}
        if name in definitions:
            if json.dumps(definitions[name], sort_keys=True) != json.dumps(item, sort_keys=True):
                return "conflicting_same_name", {}
            repeats = True
        definitions[name] = item
    return "identical_repeated_definitions" if repeats else "unique_definitions", definitions


def parameter_name_findings(calls: list[dict], definitions: dict) -> set[str]:
    """Check only declared and required names, not full JSON Schema validity."""
    findings = set()
    for call in calls:
        if call["name"] not in definitions:
            findings.add("tool_not_declared")
            continue
        schema = definitions[call["name"]]["parameters"]
        properties, required = schema.get("properties", {}), schema.get("required", [])
        if not isinstance(properties, dict) or not isinstance(required, list) or not all(isinstance(k, str) for k in required):
            findings.add("unsupported_parameter_name_schema")
            continue
        if not set(required) <= set(properties):
            findings.add("schema_requires_undeclared_property")
        if not set(required) <= set(call["arguments"]):
            findings.add("missing_required_argument")
        if set(call["arguments"]) - set(properties):
            findings.add("argument_not_in_declared_properties")
    return findings


def diagnose(rows: list[dict]) -> dict:
    definitions_count: Counter = Counter()
    call_failures: Counter = Counter()
    positions: Counter = Counter()
    row_groups: Counter = Counter()
    evidence = []
    for record_index, row in enumerate(rows):
        reason, definitions = definition_diagnosis(row["system"])
        definitions_count[reason] += 1
        turns = row["conversations"]
        row_has_screened_position = False
        for i, turn in enumerate(turns):
            if turn["from"] != "tool":
                continue
            previous = literal_tool_calls(turns[i - 1]["value"]) if i and turns[i - 1]["from"] == "assistant" else None
            if previous is None:
                try:
                    ast.parse(turns[i - 1]["value"] if i else "", mode="eval")
                    call_failures["unsupported_ast_or_literal"] += 1
                except (SyntaxError, ValueError, RecursionError):
                    call_failures["python_expression_syntax_error"] += 1
            if i + 1 >= len(turns) or turns[i + 1]["from"] != "assistant":
                continue
            following = literal_tool_calls(turns[i + 1]["value"])
            if following is None:
                continue
            positions["tool_then_parsed_call"] += 1
            flags = set()
            if not definitions:
                flags.add("unresolved_definitions")
            else:
                flags |= parameter_name_findings(following, definitions)
            names = result_names(turn["value"])
            if previous is None or names is None or Counter(names) != Counter(c["name"] for c in previous):
                flags.add("unresolved_previous_call_result_pair")
            if flags:
                positions.update(flags)
            else:
                positions["passes_name_and_pair_checks_only"] += 1
                row_has_screened_position = True
            evidence.append({"record_index_zero_based": record_index, "tool_turn_index_zero_based": i, "definition_status": reason, "findings": sorted(flags)})
        if row_has_screened_position:
            row_groups[reason] += 1
    return {
        "status": "readonly_diagnostics_not_candidate_inclusion",
        "rows": len(rows), "definitions": dict(definitions_count),
        "unparsed_previous_calls": dict(call_failures),
        "position_counts": dict(positions),
        "rows_passing_name_and_pair_checks_by_definition_status": dict(row_groups),
        "position_evidence": evidence,
        "limits": ["No source file modified or repaired.", "Identical repeats compared for diagnostics only; conflicting definitions not selected.", "Name checks do not validate argument types, nested schemas, authorization, or safety labels.", "No source attribution or cross-split clearance implied."],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Refusing to overwrite diagnostics")
    payload = (ROOT / "data/raw/toolsafety/toolsafety.json").read_bytes()
    if hashlib.sha256(payload).hexdigest() != SOURCE_SHA:
        raise ValueError("Pinned source hash mismatch")
    report = diagnose(json.loads(payload))
    report["source_sha256"] = SOURCE_SHA
    report["implementation_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__), ROOT / "src/intentfence/trajectory_audit.py")}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({key: value for key, value in report.items() if key != "position_evidence"}, indent=2))
