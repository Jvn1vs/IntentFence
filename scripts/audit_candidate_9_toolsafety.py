"""Audit verified ToolSafety structure without conversion, labeling, or execution."""

from __future__ import annotations

import argparse
import hashlib
import json
import unicodedata
from collections import Counter
from pathlib import Path

from intentfence.trajectory_audit import declared_tools, literal_tool_calls, result_names

ROOT = Path(__file__).resolve().parents[1]


def digest(text: str) -> str:
    normalized = " ".join(unicodedata.normalize("NFKC", text).casefold().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def audit() -> dict:
    directory = ROOT / "data/raw/toolsafety"
    manifest_bytes = (directory / "source_manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest["source"]["revision"] != "7c444473e0dc0a822247858c249b10856ade04ef":
        raise ValueError("Unexpected source revision")
    if manifest["files"]["toolsafety.json"]["sha256"] != "e623a0e72b2faf5270876462dc8a3197967c533b00755a80050187db34bcbd72":
        raise ValueError("Unexpected source digest")
    if set(manifest["files"]) != {"toolsafety.json", "README.md"}:
        raise ValueError("Unexpected source file set")
    for name, evidence in manifest["files"].items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory.resolve()):
            raise ValueError("Source file escapes raw directory")
        payload = path.read_bytes()
        if len(payload) != evidence["size"] or hashlib.sha256(payload).hexdigest() != evidence["sha256"]:
            raise ValueError("Source hash/size mismatch")
    rows = json.loads((directory / "toolsafety.json").read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("Expected a list of records")
    counts: Counter = Counter()
    patterns: Counter = Counter()
    roles: Counter = Counter()
    tools: Counter = Counter()
    unique_goals, unique_trajectories, unique_systems = set(), set(), set()
    for row in rows:
        if set(row) != {"system", "conversations"} or not isinstance(row["system"], str):
            raise ValueError("Unexpected source record schema")
        turns = row["conversations"]
        if not isinstance(turns, list) or not turns:
            raise ValueError("Empty or invalid conversation")
        for turn in turns:
            if set(turn) != {"from", "value"} or not all(isinstance(v, str) for v in turn.values()):
                raise ValueError("Unexpected conversation turn schema")
        pattern = tuple(turn["from"] for turn in turns)
        patterns["/".join(pattern)] += 1
        roles.update(pattern)
        unique_systems.add(digest(row["system"]))
        definitions = declared_tools(row["system"])
        counts["rows_with_parsed_tool_definitions" if definitions is not None else "rows_with_unparsed_tool_definitions"] += 1
        unique_trajectories.add(digest(json.dumps(row, ensure_ascii=False, sort_keys=True)))
        if turns[0]["from"] == "user":
            unique_goals.add(digest(turns[0]["value"]))
        counts["rows_with_tool_messages" if "tool" in pattern else "rows_without_tool_messages"] += 1
        row_has_pair = False
        for i, turn in enumerate(turns):
            if turn["from"] == "assistant":
                calls = literal_tool_calls(turn["value"])
                counts["parsed_call_turns" if calls is not None else "other_assistant_turns"] += 1
                if calls:
                    tools.update(call["name"] for call in calls)
                    for call in calls:
                        counts["parsed_calls_declared" if definitions is not None and call["name"] in definitions else "parsed_calls_definition_unresolved"] += 1
                continue
            if turn["from"] != "tool":
                continue
            names = result_names(turn["value"])
            before = literal_tool_calls(turns[i - 1]["value"]) if i and turns[i - 1]["from"] == "assistant" else None
            counts["tool_results_named_json" if names is not None else "tool_results_other_format"] += 1
            if before is not None and names is not None and Counter(names) == Counter(c["name"] for c in before):
                counts["tool_results_matching_previous_call_names"] += 1
            else:
                counts["tool_results_unresolved_previous_call_pair"] += 1
                counts["previous_call_unparsed" if before is None else "parsed_previous_name_mismatch"] += 1
            if i + 1 < len(turns) and turns[i + 1]["from"] == "assistant":
                after = literal_tool_calls(turns[i + 1]["value"])
                counts["tool_followed_by_parsed_call" if after is not None else "tool_followed_by_other_assistant"] += 1
                row_has_pair |= after is not None
                if after is not None and definitions is not None and all(c["name"] in definitions for c in after):
                    counts["tool_followed_by_call_with_declared_names"] += 1
        counts["rows_with_tool_then_parsed_call"] += row_has_pair
    return {
        "status": "readonly_structure_audited_not_training_ready",
        "source_revision": manifest["source"]["revision"],
        "source_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "source_files": manifest["files"],
        "implementation_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (
            Path(__file__), ROOT / "src/intentfence/trajectory_audit.py"
        )},
        "rows": len(rows),
        "counts": dict(counts),
        "roles": dict(roles),
        "patterns": dict(patterns),
        "unique_normalized_goals": len(unique_goals),
        "unique_normalized_full_records": len(unique_trajectories),
        "unique_normalized_system_prompts": len(unique_systems),
        "distinct_parsed_tool_names": len(tools),
        "top_parsed_tool_names": tools.most_common(15),
        "limitations": [
            "Parser coverage is structural, not a safety label or real-execution proof.",
            "No labels assigned, no conversion, no model or tool execution.",
            "No cross-source/locked-set near-duplicate clearance performed yet.",
            "No full upstream attribution/terms audit completed yet.",
            "One trajectory may yield multiple dependent action pairs; split by trajectory/family.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Refusing to overwrite an existing audit")
    result = audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))
