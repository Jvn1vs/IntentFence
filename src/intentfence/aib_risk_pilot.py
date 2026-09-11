"""Typed, source-literal offline contrasts; no upstream action is dispatched."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from intentfence.offline_actions import Message, SourceBinding, Span, StrictModel, Text, digest

CONTRACTS = {
    "return_result": ("content",),
    "chat_post": ("recipient", "body"),
    "issue_update": ("issue", "status", "resolution"),
    "bucket_policy": ("bucket", "effect", "principal", "action", "resource"),
}


class LiteralRequest(StrictModel):
    operation: Literal["return_result", "chat_post", "issue_update", "bucket_policy"]
    parameters: dict[str, Span]

    @model_validator(mode="after")
    def exact_contract(self) -> LiteralRequest:
        if set(self.parameters) != set(CONTRACTS[self.operation]):
            raise ValueError("missing or unsupported parameters")
        return self


class RiskPilotCase(StrictModel):
    source: SourceBinding
    conversation_boundary: int = Field(gt=0)
    prefix: list[Message]
    current_user: int = Field(ge=0)
    authorization: Span
    attack_evidence: Span
    goal_request: LiteralRequest
    content_request: LiteralRequest
    preparation_author: Literal["Codex/AI"]
    preparation_reason: Text

    def read(self, span: Span) -> str:
        if span.message >= len(self.prefix):
            raise ValueError("span outside prefix")
        content = self.prefix[span.message].content
        if not 0 <= span.start < span.end <= len(content):
            raise ValueError("invalid source span")
        return content[span.start:span.end]

    @model_validator(mode="after")
    def source_fields(self) -> RiskPilotCase:
        if len(self.prefix) != self.conversation_boundary + 1:
            raise ValueError("prefix boundary mismatch")
        users = [i for i, m in enumerate(self.prefix) if m.role == "user"]
        if not users or self.current_user != users[-1]:
            raise ValueError("current user must be latest user")
        self.read(self.authorization)
        self.read(self.attack_evidence)
        if self.authorization.message != self.current_user:
            raise ValueError("authorization must originate in current user")
        if self.prefix[self.attack_evidence.message].role != "tool_result":
            raise ValueError("attack evidence must remain low trust")
        for request in [self.goal_request, self.content_request]:
            for span in request.parameters.values():
                self.read(span)
                if self.prefix[span.message].role not in {"user", "tool_result"}:
                    raise ValueError("unsupported parameter source")
        # A copied user payload is allowed in a forwarding counterfactual; at
        # least one field must come from the low-trust instruction itself.
        if not any(s.message == self.attack_evidence.message
                   and self.attack_evidence.start <= s.start < s.end <= self.attack_evidence.end
                   for s in self.content_request.parameters.values()):
            raise ValueError("content request has no parameter in attack evidence")
        return self


def build_contrast(row_bytes: bytes, case: RiskPilotCase) -> dict:
    case = RiskPilotCase.model_validate(case.model_dump())
    if hashlib.sha256(row_bytes).hexdigest() != case.source.row_sha256:
        raise ValueError("row hash mismatch")
    row = json.loads(row_bytes)
    if row["id"] != case.source.case_id:
        raise ValueError("case ID mismatch")
    if case.conversation_boundary > len(row["conversation"]):
        raise ValueError("source boundary exceeded")
    expected = [{"role": "system", "content": row["system_prompt"]}]
    for message in row["conversation"][:case.conversation_boundary]:
        if set(message) - {"role", "content", "tool"}:
            raise ValueError("unsupported source fields")
        expected.append({"role": message["role"], "content": message["content"]})
    if expected != [m.model_dump() for m in case.prefix] or expected[-1]["role"] != "tool_result":
        raise ValueError("source prefix differs from prepared prefix")
    observations = []
    for policy, request in [("goal_bounded", case.goal_request),
                            ("content_following", case.content_request)]:
        parameters = {key: case.read(span) for key, span in request.parameters.items()}
        if request.operation == "bucket_policy" and (
            parameters["effect"] not in {"Allow", "Deny"}
            or not parameters["resource"].startswith(f"arn:aws:s3:::{parameters['bucket']}/")
        ):
            raise ValueError("unsupported bucket policy literals")
        trace = {
            "policy": policy,
            "candidate_action": {"tool": f"memory.{request.operation}_proposal",
                                 "arguments": parameters},
            "field_provenance": {key: {"span": span.model_dump(),
                                       "role": case.prefix[span.message].role}
                                 for key, span in request.parameters.items()},
            "selection_method": "ai_prepared_literal_reference_resolution",
            "branch_log": ["select_current_goal_map" if policy == "goal_bounded"
                           else "select_low_trust_counterfactual_map"],
            "prefix_sha256": digest(expected),
            "executed": False, "external_side_effects": False,
        }
        observations.append(trace)
    if observations[0]["candidate_action"] == observations[1]["candidate_action"]:
        raise ValueError("contrast actions are identical")
    record = {
        "source_binding": case.source.model_dump(),
        "preparation_sha256": digest(case.model_dump()),
        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "shared_contract_sha256": hashlib.sha256(
            Path(__file__).with_name("offline_actions.py").read_bytes()).hexdigest(),
        "contract_sha256": digest(CONTRACTS),
        "conversation_boundary": case.conversation_boundary,
        "source_tools_sha256": digest(row["tools_available"]),
        "original_tool_fields": {str(i + 1): m["tool"] for i, m in enumerate(
            row["conversation"][:case.conversation_boundary]) if "tool" in m},
        "observations": observations,
        "reviewer": case.preparation_author,
        "preparation_reason": case.preparation_reason,
        "risk_label": None, "task_alignment_labels": None, "split": None,
        "human_verified": False, "training_ready": False,
    }
    record["contrast_id"] = digest(record)
    return record
