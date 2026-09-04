from __future__ import annotations

from pathlib import Path

from intentfence.constants import RISK_LABELS, TASK_ALIGNMENT_LABELS
from intentfence.route_b import load_route_b_policy
from intentfence.route_b_ai_training import (
    AI_REVIEW_MODE,
    AI_TRAINING_EVIDENCE_CLASS,
    AI_TRAINING_PROTOCOL_VERSION,
    validate_ai_training_protocol_lock,
)

ROOT = Path(__file__).resolve().parents[1]


def validate() -> list[str]:
    errors: list[str] = []
    config_path = ROOT / "configs" / "route_b_ai_training_protocol.yaml"
    protocol_path = ROOT / "docs" / "route_b_ai_training_protocol.md"
    lock_path = ROOT / "configs" / "route_b_ai_training_protocol_lock.json"
    policy = load_route_b_policy(config_path)
    if policy.get("protocol_version") != AI_TRAINING_PROTOCOL_VERSION:
        errors.append("AI training protocol version drifted")
    if policy.get("status") != "frozen":
        errors.append("AI training protocol is not frozen")
    if policy.get("selected_route") != "B-ai-assisted-engineering":
        errors.append("AI training route drifted")
    if policy.get("evidence_status") != AI_TRAINING_EVIDENCE_CLASS:
        errors.append("AI training evidence class drifted")
    if tuple(policy.get("risk_labels", ())) != RISK_LABELS:
        errors.append("AI training Risk labels drifted")
    if tuple(policy.get("task_alignment_labels", ())) != TASK_ALIGNMENT_LABELS:
        errors.append("AI training Alignment labels drifted")
    audit = policy.get("audit", {})
    if audit.get("review_mode") != AI_REVIEW_MODE:
        errors.append("AI training audit mode is not dual_ai_engineering")
    if audit.get("independent_human_reviewers_required") != 0:
        errors.append("AI training route must have zero required human reviewers")
    if audit.get("independent_ai_reviewers_required") != 2:
        errors.append("AI training route must require exactly two AI reviewers")
    if audit.get("ai_review_counts_as_independent_human_review") is not False:
        errors.append("AI training route must not count AI as human review")
    if audit.get("temperature_must_equal") != 0:
        errors.append("AI training reviewer temperature is not fixed at zero")
    if policy.get("ai_training", {}).get("owner_must_execute") is not True:
        errors.append("AI engineering training is not owner-executed")
    if policy.get("final_test", {}).get("locked") is not True:
        errors.append("AI training route final-test lock drifted")
    if policy.get("calibration", {}).get("locked") is not True:
        errors.append("AI training route calibration lock drifted")
    readiness = policy.get("readiness", {})
    for field in ("human_verified", "formal_training_authorized", "engineering_training_authorized"):
        if readiness.get(field) is not False:
            errors.append(f"AI training route must keep readiness {field}=false")
    for relative in (
        "configs/route_b_ai_training_protocol.yaml",
        "configs/route_b_ai_review_protocol.yaml",
        "configs/route_b_ai_training_protocol_lock.json",
        "docs/route_b_ai_training_protocol.md",
        "reports/data_quality/route_b_candidate_8_ai_engineering_card.md",
        "scripts/build_route_b_ai_training_readiness.py",
        "scripts/freeze_route_b_ai_training_protocol.py",
        "src/intentfence/route_b_ai_training.py",
    ):
        if not (ROOT / relative).is_file():
            errors.append(f"AI training framework file is missing: {relative}")
    if not errors:
        try:
            validate_ai_training_protocol_lock(
                lock_path=lock_path,
                policy_path=config_path,
                protocol_document=protocol_path,
            )
        except (OSError, ValueError, KeyError) as exc:
            errors.append(f"AI training protocol lock validation failed: {exc}")
    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Route B AI-assisted engineering training framework validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
