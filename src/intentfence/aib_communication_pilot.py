"""Exact source binding for the small note/email adaptation pilot."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import Field

from intentfence.communication_actions import (
    CommunicationConfig,
    CommunicationScenario,
    select_communication_action,
)
from intentfence.offline_actions import SourceBinding, StrictModel, Text, digest


class CommunicationCase(StrictModel):
    source: SourceBinding
    conversation_boundary: int = Field(gt=0)
    scenario: CommunicationScenario
    reviewer: Literal["Codex/AI"]
    review: Text


def bind_communication(row_bytes: bytes, case: CommunicationCase) -> dict:
    case = CommunicationCase.model_validate(case.model_dump())
    if hashlib.sha256(row_bytes).hexdigest() != case.source.row_sha256:
        raise ValueError("row hash mismatch")
    row = json.loads(row_bytes)
    if row["id"] != case.source.case_id or row["id"] != case.scenario.case_id:
        raise ValueError("case identity mismatch")
    boundary = case.conversation_boundary
    if boundary > len(row["conversation"]):
        raise ValueError("boundary outside source")
    prefix = [{"role": "system", "content": row["system_prompt"]}]
    tool_fields = {}
    for index, message in enumerate(row["conversation"][:boundary]):
        if set(message) - {"role", "content", "tool"}:
            raise ValueError("unsupported source message fields")
        prefix.append({"role": message["role"], "content": message["content"]})
        if "tool" in message:
            tool_fields[str(index + 1)] = message["tool"]
    if [m.model_dump() for m in case.scenario.prefix] != prefix:
        raise ValueError("source prefix was rewritten or future content included")
    if prefix[-1]["role"] not in {"user", "tool_result"}:
        raise ValueError("boundary must precede an assistant decision")
    trace = select_communication_action(case.scenario, "goal_bounded",
                                       CommunicationConfig(scope="quarantined_source_pilot"))
    record = {
        "source_binding": case.source.model_dump(),
        "conversation_boundary": boundary,
        "source_paths": ["system_prompt"] + [f"conversation[{i}].content" for i in range(boundary)],
        "original_tool_fields": tool_fields,
        "source_tools_sha256": digest(row["tools_available"]),
        "source_tools_not_executed_or_trusted": True,
        "preparation_sha256": digest(case.model_dump()),
        "observation": trace,
        "status": ("missing_fields_quarantined" if trace["candidate_action"]["tool"]
                   == "memory.clarification" else "proposal_quarantined"),
        "reviewer": case.reviewer, "review": case.review,
        "human_verified": False, "training_ready": False,
        "risk_label": None, "task_alignment_label": None, "split": None,
    }
    record["bound_observation_id"] = digest(record)
    return record
