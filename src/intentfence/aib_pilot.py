"""Bind reviewed adaptation spans to an exact AIB row before offline selection."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import Field

from intentfence.offline_actions import (
    Digest,
    Policy,
    PolicyConfig,
    Scenario,
    StrictModel,
    Text,
    digest,
    select_action,
)


class PilotCase(StrictModel):
    case_id: Text
    row_sha256: Digest  # exact UTF-8 row bytes, excluding line terminator
    conversation_boundary: int = Field(gt=0)
    scenario: Scenario
    policies: list[Policy]
    review: Text
    reviewer: Literal["Codex/AI"]


def bind_and_select(row_bytes: bytes, case: PilotCase, *, revision: str, source_hash: str) -> dict:
    case = PilotCase.model_validate(case.model_dump())
    if hashlib.sha256(row_bytes).hexdigest() != case.row_sha256:
        raise ValueError("source row hash mismatch")
    row = json.loads(row_bytes)
    scenario = case.scenario
    if row["id"] != case.case_id or scenario.source.case_id != case.case_id:
        raise ValueError("case identity mismatch")
    if (scenario.source.revision != revision or scenario.source.file_sha256 != source_hash
            or scenario.source.row_sha256 != case.row_sha256):
        raise ValueError("source binding mismatch")
    boundary = case.conversation_boundary
    if boundary > len(row["conversation"]):
        raise ValueError("boundary exceeds source conversation")
    # System text is preserved, with an explicit index offset of one. Original
    # per-message tool fields remain in this separate projection receipt.
    expected = [{"role": "system", "content": row["system_prompt"]}]
    paths = ["system_prompt"]
    tool_fields = {}
    for index, message in enumerate(row["conversation"][:boundary]):
        if set(message) - {"role", "content", "tool"}:
            raise ValueError("unsupported source message fields")
        expected.append({"role": message["role"], "content": message["content"]})
        paths.append(f"conversation[{index}].content")
        if "tool" in message:
            tool_fields[str(index + 1)] = message["tool"]
    if [m.model_dump() for m in scenario.prefix] != expected:
        raise ValueError("prepared prefix differs from exact source projection")
    if expected[-1]["role"] not in {"user", "tool_result"}:
        raise ValueError("boundary must precede a new assistant decision")
    if not case.policies or len(case.policies) != len(set(case.policies)):
        raise ValueError("empty or duplicate policies")
    traces = [select_action(scenario, policy, PolicyConfig(scope="quarantined_source_pilot"))
              for policy in case.policies]
    return {
        "case_id": case.case_id,
        "status": "ai_prepared_quarantined",
        "preparation_sha256": digest(case.model_dump()),
        "source_paths_by_prefix_index": paths,
        "original_tool_fields": tool_fields,
        "source_tools_sha256": digest(row["tools_available"]),
        "source_tools_are_not_executed_or_treated_as_trusted_contracts": True,
        "conversation_boundary": boundary,
        "observations": traces,
        "reviewer": case.reviewer,
        "review": case.review,
        "risk_label": None,
        "task_alignment_label": None,
        "split": None,
        "human_verified": False,
        "training_ready": False,
    }
