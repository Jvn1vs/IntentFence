from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class _StringEnum(str, Enum):
    """Python 3.10-compatible subset of enum.StrEnum."""

    def __str__(self) -> str:
        return self.value


class Decision(_StringEnum):
    ALLOW = "allow"
    CONFIRM = "confirm"
    BLOCK = "block"


class ToolType(_StringEnum):
    READ = "read"
    LOCAL_WRITE = "local_write"
    EXTERNAL_COMMUNICATION = "external_communication"
    SENSITIVE = "sensitive"


@dataclass(frozen=True)
class PolicyResult:
    decision: Decision
    policy_risk_score: float
    reason_codes: tuple[str, ...]
    policy_version: str


@dataclass(frozen=True)
class PolicyConfig:
    version: str
    allow_max: float
    block_min: float
    tool_weights: dict[str, float]
    sensitive_always_confirm: bool = True
    external_communication_minimum: str = "confirm"
    fail_open_tool_types: tuple[str, ...] = ("read",)
    fail_closed_tool_types: tuple[str, ...] = ("external_communication", "sensitive")

    @classmethod
    def from_yaml(cls, path: str | Path) -> PolicyConfig:
        payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        rules = payload.get("rules", {})
        return cls(
            version=str(payload["version"]),
            allow_max=float(payload["thresholds"]["allow_max"]),
            block_min=float(payload["thresholds"]["block_min"]),
            tool_weights={key: float(value) for key, value in payload["tool_weights"].items()},
            sensitive_always_confirm=bool(rules.get("sensitive_always_confirm", True)),
            external_communication_minimum=str(
                rules.get("external_communication_minimum", "confirm")
            ),
            fail_open_tool_types=tuple(rules.get("fail_open_tool_types", ["read"])),
            fail_closed_tool_types=tuple(
                rules.get("fail_closed_tool_types", ["external_communication", "sensitive"])
            ),
        )


class PolicyEngine:
    def __init__(self, config: PolicyConfig):
        if not 0 <= config.allow_max < config.block_min:
            raise ValueError("Require 0 <= allow_max < block_min")
        self.config = config

    @classmethod
    def from_yaml(cls, path: str | Path) -> PolicyEngine:
        return cls(PolicyConfig.from_yaml(path))

    def evaluate(
        self,
        *,
        attack_probability: float,
        alignment_conflict_probability: float,
        tool_type: ToolType,
        calibrated: bool,
    ) -> PolicyResult:
        if not 0 <= attack_probability <= 1 or not 0 <= alignment_conflict_probability <= 1:
            raise ValueError("Probabilities must be in [0, 1]")

        weight = self.config.tool_weights[tool_type.value]
        model_risk = max(attack_probability, alignment_conflict_probability)
        policy_risk = model_risk * weight
        reasons: list[str] = []

        if not calibrated:
            reasons.append("uncalibrated_score")
        if policy_risk >= self.config.block_min:
            decision = Decision.BLOCK
            reasons.append("risk_above_block_threshold")
        elif policy_risk > self.config.allow_max:
            decision = Decision.CONFIRM
            reasons.append("risk_above_allow_threshold")
        else:
            decision = Decision.ALLOW
            reasons.append("risk_below_allow_threshold")

        if tool_type == ToolType.SENSITIVE and self.config.sensitive_always_confirm:
            if decision == Decision.ALLOW:
                decision = Decision.CONFIRM
            reasons.append("sensitive_tool_requires_confirmation")
        if tool_type == ToolType.EXTERNAL_COMMUNICATION and decision == Decision.ALLOW:
            decision = Decision.CONFIRM
            reasons.append("external_communication_minimum_confirmation")
        if not calibrated and tool_type != ToolType.READ and decision == Decision.ALLOW:
            decision = Decision.CONFIRM
            reasons.append("uncalibrated_non_read_requires_confirmation")

        return PolicyResult(
            decision=decision,
            policy_risk_score=float(policy_risk),
            reason_codes=tuple(dict.fromkeys(reasons)),
            policy_version=self.config.version,
        )

    def on_detector_failure(self, tool_type: ToolType) -> PolicyResult:
        if tool_type.value in self.config.fail_closed_tool_types:
            return PolicyResult(
                Decision.BLOCK,
                2.0,
                ("detector_failure", "fail_closed_tool"),
                self.config.version,
            )
        if tool_type.value in self.config.fail_open_tool_types:
            return PolicyResult(
                Decision.ALLOW,
                0.0,
                ("detector_failure", "restricted_fail_open"),
                self.config.version,
            )
        return PolicyResult(
            Decision.CONFIRM,
            1.0,
            ("detector_failure", "manual_confirmation_required"),
            self.config.version,
        )

    def metadata(self) -> dict[str, Any]:
        return {
            "version": self.config.version,
            "allow_max": self.config.allow_max,
            "block_min": self.config.block_min,
            "tool_weights": self.config.tool_weights,
        }
