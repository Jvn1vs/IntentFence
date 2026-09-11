"""Offline note/email proposals with explicit references and recipient roles.

Reference selection is prepared by an author, not inferred from natural language.
No file, note service, mailbox, network or subprocess is accessed by these adapters.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from intentfence.offline_actions import Message, Span, StrictModel, Text, digest


class Reference(StrictModel):
    # Empty means unavailable; multiple candidates mean unresolved anaphora.
    candidates: list[Span]
    current_user_authorization: Span | None = None


class NoteRequest(StrictModel):
    operation: Literal["note"]
    title: Reference
    body: Reference


class EmailRequest(StrictModel):
    operation: Literal["email"]
    to: list[Reference]
    cc: list[Reference]
    bcc: list[Reference]
    body: Reference


Request = Annotated[NoteRequest | EmailRequest, Field(discriminator="operation")]


class CommunicationConfig(StrictModel):
    schema_version: Literal[1] = 1
    scope: Literal["synthetic_fixtures_only", "quarantined_source_pilot"] = "synthetic_fixtures_only"
    ambiguous_reference: Literal["clarify"] = "clarify"
    missing_body: Literal["clarify"] = "clarify"


class CommunicationScenario(StrictModel):
    case_id: Text
    prefix: list[Message]
    decision_boundary: int = Field(gt=0)
    current_user: int = Field(ge=0)
    goal: Request
    suggested: Request | None = None
    suggestion_evidence: Span | None = None
    preparation_author: Literal["Codex/AI"]
    preparation_reason: Text

    def read(self, span: Span) -> str:
        if span.message >= len(self.prefix):
            raise ValueError("reference outside action prefix")
        content = self.prefix[span.message].content
        if not 0 <= span.start < span.end <= len(content):
            raise ValueError("invalid reference range")
        return content[span.start:span.end]

    @model_validator(mode="after")
    def validate_boundary(self) -> CommunicationScenario:
        if self.decision_boundary != len(self.prefix):
            raise ValueError("prefix must end exactly at the decision boundary")
        users = [i for i, m in enumerate(self.prefix) if m.role == "user"]
        if not users or self.current_user != users[-1]:
            raise ValueError("authorization must bind the latest user turn")
        for request in [self.goal, self.suggested]:
            if request is None:
                continue
            for _, reference in references(request):
                for span in reference.candidates:
                    self.read(span)
                    if self.prefix[span.message].role == "system":
                        raise ValueError("system instructions are not note/email content facts")
                evidence = reference.current_user_authorization
                if evidence is not None:
                    self.read(evidence)
                    if evidence.message != self.current_user:
                        raise ValueError("stale or non-user authorization")
        if (self.suggested is None) != (self.suggestion_evidence is None):
            raise ValueError("suggested request requires separate low-trust evidence")
        if self.suggestion_evidence is not None:
            self.read(self.suggestion_evidence)
            if self.prefix[self.suggestion_evidence.message].role not in {
                "tool_result", "tool_description"
            }:
                raise ValueError("suggestion evidence must originate in low-trust content")
        return self


def references(request: NoteRequest | EmailRequest) -> list[tuple[str, Reference]]:
    if isinstance(request, NoteRequest):
        return [("title", request.title), ("body", request.body)]
    result = [(f"{role}[{index}]", ref) for role in ["to", "cc", "bcc"]
              for index, ref in enumerate(getattr(request, role))]
    return [*result, ("body", request.body)]


def select_communication_action(
    scenario: CommunicationScenario,
    policy: Literal["goal_bounded", "content_following"],
    config: CommunicationConfig | None = None,
) -> dict:
    scenario = CommunicationScenario.model_validate(scenario.model_dump())
    config = CommunicationConfig.model_validate((config or CommunicationConfig()).model_dump())
    if policy not in {"goal_bounded", "content_following"}:
        raise ValueError("unsupported communication policy")
    request = scenario.goal if policy == "goal_bounded" else scenario.suggested
    issues: list[str] = []
    values: dict[str, str] = {}
    provenance = {}
    if request is None:
        issues.append("missing_suggested_request")
    else:
        if isinstance(request, EmailRequest) and not request.to:
            issues.append("missing:to")
        for name, reference in references(request):
            if len(reference.candidates) != 1:
                issues.append(f"{'missing' if not reference.candidates else 'ambiguous'}:{name}")
                continue
            span = reference.candidates[0]
            value = scenario.read(span)
            if not value.strip():
                issues.append(f"empty:{name}")
                continue
            if policy == "goal_bounded" and reference.current_user_authorization is None:
                issues.append(f"authorization_unknown:{name}")
            # A recipient is one exact address literal, not a joined recipient list
            # or header fragment. This is a limited fixture grammar, not RFC validation.
            if name.startswith(("to[", "cc[", "bcc[")) and (
                value.count("@") != 1 or any(c.isspace() or c in ",;<>:" for c in value)
                or any(not part for part in value.split("@"))
            ):
                issues.append(f"unsupported_address_literal:{name}")
            values[name] = value
            provenance[name] = {
                "source_span": span.model_dump(),
                "source_role": scenario.prefix[span.message].role,
                "authorization": (reference.current_user_authorization.model_dump()
                                  if reference.current_user_authorization else None),
            }
    if issues:
        action = {"tool": "memory.clarification", "arguments": {"issues": issues}}
    elif isinstance(request, NoteRequest):
        action = {"tool": "memory.note_save_proposal", "arguments": values}
    else:
        assert isinstance(request, EmailRequest)
        arguments = {role: [values[f"{role}[{i}]"] for i in range(len(getattr(request, role)))]
                     for role in ["to", "cc", "bcc"]}
        action = {"tool": "memory.email_send_proposal",
                  "arguments": {**arguments, "body": values["body"]}}
    trace = {
        "schema_version": 1,
        "runtime": ("prepared_communication_fixture" if config.scope == "synthetic_fixtures_only"
                    else "prepared_communication_source_pilot"),
        "case_id": scenario.case_id, "policy": policy,
        "input_sha256": digest(scenario.model_dump()),
        "config_sha256": digest(config.model_dump()),
        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "shared_contract_sha256": hashlib.sha256(
            Path(__file__).with_name("offline_actions.py").read_bytes()).hexdigest(),
        "candidate_action": action,
        "resolved_field_provenance": provenance,
        "branch_log": issues or ["selected_explicit_prepared_references"],
        "preparation_author": scenario.preparation_author,
        "preparation_reason": scenario.preparation_reason,
        "executed": False, "external_side_effects": False,
        "human_verified": False, "training_ready": False,
        "risk_label": None, "task_alignment_label": None, "split": None,
    }
    trace["action_observation_id"] = digest(trace)
    return trace
