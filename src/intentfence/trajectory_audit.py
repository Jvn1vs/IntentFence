"""Read-only structural checks for source conversations; never execute tool text."""

from __future__ import annotations

import ast
import json
from typing import Any


def literal_tool_calls(text: str) -> list[dict[str, Any]] | None:
    """Recognize a restricted list of named calls with literal keyword arguments.

    None means unsupported text, not necessarily unsafe or invalid upstream data.
    The AST is inspected only: no eval, call, import, or attribute access occurs.
    """
    if not text.lstrip().startswith("[") or len(text) > 100_000:
        return None
    try:
        tree = ast.parse(text, mode="eval")
        if not isinstance(tree.body, ast.List) or not 1 <= len(tree.body.elts) <= 100:
            return None
        if sum(1 for _ in ast.walk(tree)) > 10_000:
            return None
        calls = []
        for item in tree.body.elts:
            if not isinstance(item, ast.Call) or not isinstance(item.func, ast.Name) or item.args:
                return None
            arguments = {}
            for keyword in item.keywords:
                if keyword.arg is None or keyword.arg in arguments:
                    return None
                arguments[keyword.arg] = ast.literal_eval(keyword.value)
            # Non-JSON literals are not accepted as structured API arguments.
            json.dumps(arguments, allow_nan=False)
            calls.append({"name": item.func.id, "arguments": arguments})
        return calls
    except (SyntaxError, ValueError, TypeError, RecursionError):
        return None


def result_names(text: str) -> list[str] | None:
    try:
        results = json.loads(text)
    except (ValueError, RecursionError):
        return None
    if not isinstance(results, list) or not results:
        return None
    names = []
    for result in results:
        if not isinstance(result, dict) or not isinstance(result.get("name"), str):
            return None
        if not result["name"] or "result" not in result:
            return None
        names.append(result["name"])
    return names


def declared_tools(system: str) -> dict[str, dict] | None:
    marker = "Here is a list of functions in JSON format that you can invoke:"
    if system.count(marker) != 1:
        return None
    text = system.split(marker, 1)[1].lstrip()
    try:
        definitions, _ = json.JSONDecoder().raw_decode(text)
    except (ValueError, RecursionError):
        return None
    if not isinstance(definitions, list) or not definitions:
        return None
    result = {}
    for item in definitions:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            return None
        if not item["name"] or item["name"] in result or not isinstance(item.get("parameters"), dict):
            return None
        result[item["name"]] = item
    return result
