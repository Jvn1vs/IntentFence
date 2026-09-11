"""Fixture-only deterministic action selection; never dispatches source tools.

Structured facts are an explicit, reviewed preparation layer, not an NLP parser.
Neither source labels nor future messages are accepted by the policy interface.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Text = Annotated[str, Field(min_length=1)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Operation = Literal["lookup", "return_result", "message", "file", "permission", "update"]
Policy = Literal["goal_bounded", "content_following", "stale_object", "unresolved_scope"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class SourceBinding(StrictModel):
    revision: Text
    file_sha256: Digest
    row_sha256: Digest
    case_id: Text


class Message(StrictModel):
    role: Literal["system", "user", "assistant", "tool_result", "tool_description"]
    content: Text


class Span(StrictModel):
    message: Annotated[int, Field(ge=0)]
    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(gt=0)]


class Fact(StrictModel):
    span: Span
    trust: Literal["user", "untrusted", "context"]


# Closed contracts are project-authored, never extracted from poisoned descriptions.
# Values are strings; no path, query, recipient or permission is ever executed.
ADAPTERS: dict[str, tuple[str, tuple[str, ...], str | None]] = {
    "lookup": ("memory.lookup", ("resource", "query"), "resource"),
    "return_result": ("memory.return_result", ("content",), None),
    "message": ("memory.message_proposal", ("recipient", "body"), "recipient"),
    "file": ("memory.file_proposal", ("path", "content"), "path"),
    "permission": ("memory.permission_proposal", ("resource", "principal", "access"), "resource"),
    "update": ("memory.object_update_proposal", ("object", "field", "value"), "object"),
}


class Request(StrictModel):
    operation: Operation
    arguments: dict[str, Text]  # parameter -> fact ID, never literal arguments

    @model_validator(mode="after")
    def parameter_names(self) -> Request:
        if set(self.arguments) != set(ADAPTERS[self.operation][1]):
            raise ValueError("missing or unexpected adapter parameters")
        return self


class Authorization(StrictModel):
    status: Literal["known", "unknown"]
    # Exact full argument grants; absence is not implicit permission.
    grants: list[Request]
    evidence: list[Span]


class Scenario(StrictModel):
    source: SourceBinding
    prefix: list[Message]
    decision_boundary: Annotated[int, Field(gt=0)]  # exclusive prefix length
    user_goal: Span
    facts: dict[str, Fact]
    goal: Request
    suggestion: Span | None = None  # JSON {operation, arguments:{name:fact_id}}
    authorization: Authorization
    trusted_contract_origin: Literal["project_authored_fixture_v1"]
    fixture_mapping_version: Text
    fixture_world: dict[str, str]
    scenario_group: Text

    def text(self, span: Span) -> str:
        if span.message >= len(self.prefix):
            raise ValueError("span outside decision prefix")
        content = self.prefix[span.message].content
        if not 0 <= span.start < span.end <= len(content):
            raise ValueError("invalid source span")
        return content[span.start:span.end]

    def resolve(self, request: Request) -> tuple[dict[str, str], dict[str, dict]]:
        values, provenance = {}, {}
        for parameter, fact_id in request.arguments.items():
            if fact_id not in self.facts:
                raise ValueError(f"missing source fact: {fact_id}")
            fact = self.facts[fact_id]
            values[parameter] = self.text(fact.span)
            provenance[parameter] = {"fact_id": fact_id, **fact.model_dump()}
        return values, provenance

    @model_validator(mode="after")
    def boundaries(self) -> Scenario:
        if self.decision_boundary != len(self.prefix):
            raise ValueError("only the exact action prefix is accepted")
        self.text(self.user_goal)
        user_indices = [i for i, m in enumerate(self.prefix) if m.role == "user"]
        if not user_indices or self.user_goal.message != user_indices[-1]:
            raise ValueError("goal must reference latest user message")
        for fact in self.facts.values():
            self.text(fact.span)
            role = self.prefix[fact.span.message].role
            if fact.trust == "user" and role != "user":
                raise ValueError("user fact must originate in user message")
            if fact.trust == "untrusted" and role not in {"tool_result", "tool_description"}:
                raise ValueError("untrusted fact must originate in a low-trust carrier")
            if fact.trust == "context" and role != "assistant":
                raise ValueError("context fact must originate in prior assistant context")
        self.resolve(self.goal)
        if any(self.facts[f].trust != "user" for f in self.goal.arguments.values()):
            raise ValueError("fixture goal arguments must be user grounded")
        for grant in self.authorization.grants:
            self.resolve(grant)
            if any(self.facts[f].trust != "user" for f in grant.arguments.values()):
                raise ValueError("authorization cannot originate in untrusted facts")
        if self.authorization.status == "known" and not self.authorization.evidence:
            raise ValueError("known authorization requires evidence")
        for span in self.authorization.evidence:
            self.text(span)
            if self.prefix[span.message].role != "user":
                raise ValueError("authorization evidence must be user grounded")
        if self.suggestion is not None:
            self.text(self.suggestion)
            if self.prefix[self.suggestion.message].role not in {"tool_result", "tool_description"}:
                raise ValueError("suggestion must be low trust")
        return self


class PolicyConfig(StrictModel):
    schema_version: Literal[1] = 1
    scope: Literal["synthetic_fixtures_only"] = "synthetic_fixtures_only"
    stale_selection: Literal["first_fact_id_different_value"] = "first_fact_id_different_value"


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")).hexdigest()


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate suggestion JSON key")
        result[key] = value
    return result


def select_action(
    scenario: Scenario, policy: Policy, config: PolicyConfig | None = None
) -> dict:
    """Select and record a proposal in a copied memory world, without executing it.

    A caller may prepare fixtures, but cannot pass labels, execution constraints or
    a whole source conversation. There is deliberately no dataset loader or writer.
    """
    # Revalidate nested mutable containers, including model_copy/model_construct inputs.
    scenario = Scenario.model_validate(scenario.model_dump())
    config = PolicyConfig.model_validate((config or PolicyConfig()).model_dump())
    if policy not in {"goal_bounded", "content_following", "stale_object", "unresolved_scope"}:
        raise ValueError("unknown policy")
    request = scenario.goal
    branches = []
    reason = None
    if policy == "content_following":
        if scenario.suggestion is None:
            reason = "missing_structured_suggestion"
        else:
            request = Request.model_validate(json.loads(
                scenario.text(scenario.suggestion), object_pairs_hook=_unique_object
            ))
            scenario.resolve(request)
            if any(scenario.facts[f].trust != "untrusted" for f in request.arguments.values()):
                raise ValueError("suggestion arguments must have low-trust provenance")
            branches.append("parsed_exact_low_trust_json_span")
    elif policy == "stale_object":
        parameter = ADAPTERS[request.operation][2]
        if parameter is None:
            reason = "adapter_has_no_object_parameter"
        else:
            current = scenario.text(scenario.facts[request.arguments[parameter]].span)
            # Context candidates must precede the latest user goal. A preparer must
            # identify the same semantic object slot explicitly by naming its facts.
            candidates = sorted(
                key for key, fact in scenario.facts.items()
                if key.startswith(f"{parameter}:") and fact.trust == "context"
                and fact.span.message < scenario.user_goal.message
                and scenario.text(fact.span) != current
            )
            if not candidates:
                reason = "no_prior_object_evidence"
            else:
                request = Request(operation=request.operation, arguments={
                    **request.arguments, parameter: candidates[0]
                })
                branches.append(f"selected_prior_object:{candidates[0]}")
    else:
        arguments, _ = scenario.resolve(request)
        authorized = scenario.authorization.status == "known" and any(
            grant.operation == request.operation and scenario.resolve(grant)[0] == arguments
            for grant in scenario.authorization.grants
        )
        if not authorized:
            reason = "authorization_unknown_or_not_granted"
        else:
            branches.append("exact_goal_arguments_authorized")
    if reason:
        action = {"tool": "memory.clarification", "arguments": {"reason": reason}}
        provenance = {"reason": {"derived_from": "branch_log"}}
        branches.append(reason)
    else:
        arguments, provenance = scenario.resolve(request)
        action = {"tool": ADAPTERS[request.operation][0], "arguments": arguments}
    before = dict(scenario.fixture_world)
    # Ledger only: even memory resources are not changed by a proposal.
    after = {"resources": before, "proposals": [action]}
    trace = {
        "schema_version": 1,
        "runtime": "deterministic_fixture_policy",
        "source_binding": scenario.source.model_dump(),
        "scenario_group": scenario.scenario_group,
        "action_policy_id": policy,
        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "config_sha256": digest(config.model_dump()),
        "contract_sha256": digest(ADAPTERS),
        "input_sha256": digest(scenario.model_dump()),
        "prefix_sha256": digest([m.model_dump() for m in scenario.prefix]),
        "branch_log": branches,
        "candidate_action": action,
        "field_provenance": provenance,
        "selection_evidence": {
            "goal": scenario.user_goal.model_dump(),
            "suggestion": scenario.suggestion.model_dump() if scenario.suggestion else None,
            "authorization": scenario.authorization.model_dump(),
        },
        "memory_before_sha256": digest({"resources": before, "proposals": []}),
        "memory_after_sha256": digest(after),
        "memory_summary": {"resource_count": len(before), "proposal_count": 1},
        "executed": False,
        "external_side_effects": False,
        "human_verified": False,
        "training_ready": False,
    }
    trace["action_observation_id"] = digest(trace)
    return trace


def validate_group_roles(assignments: dict[str, str], links: list[tuple[str, str]]) -> None:
    """Reject any linked scenario component spanning roles, without creating splits.

    Caller-supplied links must include source, near-duplicate and structural family
    relations; passing this check is not evidence that those links are complete.
    """
    allowed = {"train", "validation", "calibration", "test_a", "test_b", "test_c", "test_d"}
    if not assignments or any(role not in allowed for role in assignments.values()):
        raise ValueError("missing or unknown role")
    for left, right in links:
        if left not in assignments or right not in assignments:
            raise ValueError("link endpoint missing from assignments")
        if assignments[left] != assignments[right]:
            raise ValueError("linked family crosses split roles")
