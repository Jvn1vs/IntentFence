"""Source-specific background adapters; no implied security labels or actions."""

from __future__ import annotations

from collections import Counter
from typing import Any

DOLLY_CATEGORIES = frozenset({"closed_qa", "information_extraction", "summarization"})
DOLLY_REVISION = "bdd27f4d94b9c1f951818a7da7fd7aeea5dbff1a"


def dolly_backgrounds(records: list[dict[str, Any]]) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Select grounding tasks without inventing missing context or treating answers as actions."""
    output = []
    excluded: Counter[str] = Counter()
    for index, record in enumerate(records, 1):
        for field in ("instruction", "context", "response", "category"):
            if field not in record or not isinstance(record[field], str):
                raise ValueError(f"Dolly row {index}: missing or non-string {field}")
        if record["category"] not in DOLLY_CATEGORIES:
            excluded["category_not_selected"] += 1
            continue
        if not record["context"].strip():
            excluded["missing_reference_context"] += 1
            continue
        if not record["instruction"].strip():
            excluded["missing_instruction"] += 1
            continue
        output.append(
            {
                "source": "DatabricksDolly15k",
                "source_revision": DOLLY_REVISION,
                "source_record": f"databricks/databricks-dolly-15k@{DOLLY_REVISION}:{index}",
                "task": "dolly_" + record["category"],
                "goal": record["instruction"],
                "content": record["context"],
                "attribution": "Copyright (2023) Databricks, Inc.; Wikipedia editors and contributors; CC-BY-SA-3.0",
            }
        )
    return output, dict(excluded)
