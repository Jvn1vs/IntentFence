"""Source-bound, offline git-log contrast; never writes files or pushes commits."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import model_validator

from intentfence.offline_actions import Message, SourceBinding, Span, StrictModel, digest


class GitlogCase(StrictModel):
    source: SourceBinding
    conversation_boundary: Literal[2]
    user_goal: Span
    attack_evidence: Span
    file_path: Span
    file_content: Span
    preparation_author: Literal["Codex/AI"]

    @model_validator(mode="after")
    def positions(self) -> GitlogCase:
        if self.user_goal.message != 1 or self.user_goal.start != 0:
            raise ValueError("goal must start at current user message")
        if any(span.message != 2 for span in (
            self.attack_evidence, self.file_path, self.file_content
        )):
            raise ValueError("attack and file fields must come from tool result")
        for span in (self.file_path, self.file_content):
            if not (self.attack_evidence.start <= span.start < span.end
                    <= self.attack_evidence.end):
                raise ValueError("file field lies outside attack evidence")
        return self


def _read(content: str, span: Span) -> str:
    if not 0 <= span.start < span.end <= len(content):
        raise ValueError("source span outside message")
    return content[span.start:span.end]


def build_gitlog_contrast(row_bytes: bytes, case: GitlogCase) -> dict:
    """Build two mock proposals from a frozen action prefix and reviewed spans."""
    case = GitlogCase.model_validate(case.model_dump())
    if hashlib.sha256(row_bytes).hexdigest() != case.source.row_sha256:
        raise ValueError("source row hash mismatch")
    row = json.loads(row_bytes)
    if row["id"] != case.source.case_id:
        raise ValueError("case ID mismatch")
    conversation = row["conversation"]
    if len(conversation) < case.conversation_boundary:
        raise ValueError("missing source prefix")
    if [m["role"] for m in conversation[:2]] != ["user", "tool_result"]:
        raise ValueError("unexpected source roles")
    if any(set(m) - {"role", "content", "tool"} for m in conversation[:2]):
        raise ValueError("unsupported source message fields")
    tools = row["tools_available"]
    names = [tool["name"] for tool in tools]
    if len(names) != len(set(names)) or not {"git_log", "file_write"} <= set(names):
        raise ValueError("required source tool definitions absent or duplicated")
    prefix = [Message(role="system", content=row["system_prompt"])]
    prefix.extend(Message(role=m["role"], content=m["content"])
                  for m in conversation[:2])
    user = prefix[1].content
    result = prefix[2].content
    if case.user_goal.end != len(user):
        raise ValueError("user goal must cover current request")
    _read(user, case.user_goal)
    _read(result, case.attack_evidence)
    path = _read(result, case.file_path)
    content = _read(result, case.file_content)
    prefix_hash = digest([message.model_dump() for message in prefix])
    observations = [
        {
            "policy": "goal_bounded",
            "candidate_action": {
                "tool": "memory.return_result_proposal", "arguments": {"content": result}
            },
            "field_provenance": {"content": {"role": "tool_result", "span": {
                "message": 2, "start": 0, "end": len(result)
            }}},
            "branch_log": ["return_current_git_log_as_data"],
        },
        {
            "policy": "content_following",
            "candidate_action": {
                "tool": "memory.file_proposal",
                "arguments": {"path": path, "content": content},
            },
            "field_provenance": {
                "path": {"role": "tool_result", "span": case.file_path.model_dump()},
                "content": {"role": "tool_result", "span": case.file_content.model_dump()},
            },
            "branch_log": ["select_ai_prepared_low_trust_spans"],
        },
    ]
    for observation in observations:
        observation.update({
            "prefix_sha256": prefix_hash,
            "executed": False,
            "external_side_effects": False,
            "action_provenance": "sandbox_policy_output",
            "model_generated": False,
        })
    record = {
        "source_binding": case.source.model_dump(),
        "conversation_boundary": case.conversation_boundary,
        "source_tools_sha256": digest(tools),
        "prefix_sha256": prefix_hash,
        "attack_evidence": case.attack_evidence.model_dump(),
        "preparation_sha256": digest(case.model_dump()),
        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "observations": observations,
        "reviewer": case.preparation_author,
        "risk_label": None,
        "task_alignment_labels": None,
        "split": None,
        "human_verified": False,
        "training_ready": False,
    }
    record["contrast_id"] = digest(record)
    return record
