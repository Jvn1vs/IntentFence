"""Offline numeric-answer contrasts with explicit query scope provenance."""

from __future__ import annotations

from pydantic import model_validator

from intentfence.offline_actions import Message, Span, StrictModel, digest


class ScopedResult(StrictModel):
    query: Span
    result: Span
    value: Span


class StaleResultInput(StrictModel):
    prefix: list[Message]
    latest: ScopedResult
    previous: ScopedResult

    def read(self, span: Span) -> str:
        if span.message >= len(self.prefix):
            raise ValueError("span outside prefix")
        text = self.prefix[span.message].content
        if not 0 <= span.start < span.end <= len(text):
            raise ValueError("invalid span")
        return text[span.start:span.end]

    @model_validator(mode="after")
    def check_scopes(self) -> StaleResultInput:
        users = [i for i, m in enumerate(self.prefix) if m.role == "user"]
        if not users or self.latest.query.message != users[-1]:
            raise ValueError("latest query must be current user")
        if not self.previous.query.message < self.previous.result.message < self.latest.query.message:
            raise ValueError("previous result must precede current query")
        if not self.latest.query.message < self.latest.result.message == len(self.prefix) - 1:
            raise ValueError("latest result must terminate the decision prefix")
        for item in [self.latest, self.previous]:
            for span in [item.query, item.result, item.value]:
                self.read(span)
            if self.prefix[item.query.message].role != "user":
                raise ValueError("query is not user grounded")
            if self.prefix[item.result.message].role != "tool_result":
                raise ValueError("result is not tool grounded")
            if (item.value.message != item.result.message
                    or not item.result.start <= item.value.start < item.value.end <= item.result.end):
                raise ValueError("value is outside its scoped result")
            if not self.read(item.value).isascii() or not self.read(item.value).isdigit():
                raise ValueError("only explicit unsigned integer literals are supported")
        if self.read(self.latest.value) == self.read(self.previous.value):
            raise ValueError("no distinct numeric contrast")
        return self


def select_scoped_results(value: StaleResultInput) -> list[dict]:
    value = StaleResultInput.model_validate(value.model_dump())
    result = []
    for policy, item in [("latest_result", value.latest), ("previous_result", value.previous)]:
        result.append({
            "candidate_action": {"tool": "memory.return_result_proposal",
                                 "arguments": {"content": value.read(item.value)}},
            "policy": policy, "input_sha256": digest(value.model_dump()),
            "field_provenance": {"content": item.value.model_dump()},
            "query_scope": {"query": item.query.model_dump(), "result": item.result.model_dump()},
            "selection_method": "ai_prepared_scope_then_deterministic_reference_selection",
            "executed": False, "external_side_effects": False,
        })
    return result
