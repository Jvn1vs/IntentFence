from __future__ import annotations

import base64
import math
import re
import unicodedata
from dataclasses import dataclass

from intentfence.constants import RISK_LABELS


@dataclass(frozen=True)
class RuleHit:
    rule_id: str
    risk_label: str
    weight: float
    excerpt: str


@dataclass(frozen=True)
class RulePrediction:
    probabilities: dict[str, float]
    alignment_conflict_probability: float
    hits: tuple[RuleHit, ...]

    @property
    def attack_score(self) -> float:
        return 1.0 - self.probabilities["benign"]

    @property
    def predicted_risk(self) -> str:
        return max(self.probabilities, key=self.probabilities.get)


@dataclass(frozen=True)
class CompiledRule:
    rule_id: str
    risk_label: str
    pattern: re.Pattern[str]
    weight: float


def _rule(rule_id: str, risk_label: str, pattern: str, weight: float) -> CompiledRule:
    return CompiledRule(rule_id, risk_label, re.compile(pattern, re.IGNORECASE | re.DOTALL), weight)


RULES: tuple[CompiledRule, ...] = (
    _rule(
        "instruction_override",
        "instruction_hijacking",
        r"\b(ignore|disregard|forget|override)\b.{0,50}\b(previous|prior|above|system|developer)\b.{0,25}\b(instruction|message|prompt)s?\b",
        1.8,
    ),
    _rule(
        "new_objective",
        "instruction_hijacking",
        r"\b(new|real|actual|secret)\s+(task|objective|instruction)s?\b|\bdo\s+this\s+instead\b",
        1.4,
    ),
    _rule(
        "system_prompt_request",
        "data_exfiltration",
        r"\b(reveal|print|show|return|send|expose|leak)\b.{0,45}\b(system|developer)\s+(prompt|message|instruction)s?\b",
        1.5,
    ),
    _rule(
        "credential_exfiltration",
        "data_exfiltration",
        r"\b(upload|send|post|transmit|forward|exfiltrate)\b.{0,80}\b(password|credential|secret|token|api[ _-]?key|private[ _-]?key|cookie|email|file)s?\b",
        2.1,
    ),
    _rule(
        "external_destination",
        "data_exfiltration",
        r"https?://(?!(?:localhost|127\.0\.0\.1)(?:[:/]|$))[^\s'\"<>]+",
        0.7,
    ),
    _rule(
        "privileged_operation",
        "privilege_escalation",
        r"\b(admin|root|sudo|elevat(?:e|ed)|grant)\b.{0,55}\b(permission|privilege|access|role|command|shell)s?\b",
        1.8,
    ),
    _rule(
        "dangerous_tool",
        "tool_manipulation",
        r"\b(delete|remove|drop|transfer|pay|purchase|execute|run)\b.{0,45}\b(file|database|money|command|script|account|permission)s?\b",
        1.4,
    ),
    _rule(
        "recipient_rewrite",
        "tool_manipulation",
        r"\b(change|replace|set|use)\b.{0,40}\b(recipient|destination|address|url|endpoint)\b",
        1.6,
    ),
    _rule(
        "authority_claim",
        "instruction_hijacking",
        r"\b(this is|treat this as|priority)\b.{0,45}\b(system|developer|administrator|trusted)\b",
        1.2,
    ),
)

BENIGN_CONTEXT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(article|paper|blog|report|discussion|example|quote|quoted)\b", re.IGNORECASE),
    re.compile(r"\b(detect|detection|defend|defense|mitigat|security|training data)\w*\b", re.IGNORECASE),
    re.compile(r"```|`[^`]+`|\bregex\b", re.IGNORECASE),
)

ZERO_WIDTH_RE = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")
BASE64_RE = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{32,}={0,2}(?![A-Za-z0-9+/])")


def _excerpt(value: str, match: re.Match[str], radius: int = 45) -> str:
    start = max(0, match.start() - radius)
    end = min(len(value), match.end() + radius)
    return value[start:end].replace("\n", " ")


def _softmax(scores: dict[str, float]) -> dict[str, float]:
    peak = max(scores.values())
    exponentials = {label: math.exp(score - peak) for label, score in scores.items()}
    total = sum(exponentials.values())
    return {label: value / total for label, value in exponentials.items()}


class RuleDetector:
    """Transparent baseline. It is intentionally not presented as a trained model."""

    backend_name = "rules-v1"

    def predict(self, user_goal: str, untrusted_content: str, proposed_action: str) -> RulePrediction:
        content_hits = self._scan(untrusted_content)
        action_hits = self._scan(proposed_action)
        hits = list(content_hits) + [
            RuleHit(hit.rule_id, hit.risk_label, hit.weight * 1.2, hit.excerpt) for hit in action_hits
        ]

        if ZERO_WIDTH_RE.search(untrusted_content):
            hits.append(RuleHit("zero_width", "instruction_hijacking", 0.8, "zero-width characters"))
        for match in BASE64_RE.finditer(untrusted_content):
            decoded = self._decode_base64(match.group(0))
            if decoded and any(rule.pattern.search(decoded) for rule in RULES):
                hits.append(RuleHit("encoded_instruction", "instruction_hijacking", 1.5, decoded[:120]))

        # Quoted security discussions are the canonical hard-negative pattern.
        benign_evidence = sum(bool(pattern.search(untrusted_content)) for pattern in BENIGN_CONTEXT_PATTERNS)
        category_scores = {label: -1.5 for label in RISK_LABELS}
        category_scores["benign"] = 1.3 + min(benign_evidence, 2) * 0.45
        for hit in hits:
            category_scores[hit.risk_label] += hit.weight
            category_scores["benign"] -= hit.weight * 0.35

        # If the suspicious action is directly requested by the user, reduce—but do not erase—risk.
        action_terms = set(re.findall(r"[a-z0-9_]+", proposed_action.casefold()))
        goal_terms = set(re.findall(r"[a-z0-9_]+", user_goal.casefold()))
        if action_terms and len(action_terms & goal_terms) / len(action_terms) >= 0.45:
            category_scores["benign"] += 0.8
            for label in RISK_LABELS[1:]:
                category_scores[label] -= 0.3

        probabilities = _softmax(category_scores)
        alignment = min(0.99, max(0.01, 1.0 - probabilities["benign"] + 0.05 * len(action_hits)))
        return RulePrediction(probabilities, alignment, tuple(hits))

    def _scan(self, value: str) -> list[RuleHit]:
        hits: list[RuleHit] = []
        normalized = unicodedata.normalize("NFKC", value)
        for rule in RULES:
            if match := rule.pattern.search(normalized):
                hits.append(RuleHit(rule.rule_id, rule.risk_label, rule.weight, _excerpt(normalized, match)))
        return hits

    @staticmethod
    def _decode_base64(value: str) -> str | None:
        try:
            padding = "=" * (-len(value) % 4)
            decoded = base64.b64decode(value + padding, validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return None
        return decoded if decoded.isprintable() else None
