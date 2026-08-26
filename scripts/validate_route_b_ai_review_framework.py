from __future__ import annotations

from pathlib import Path

from intentfence.constants import RISK_LABELS, TASK_ALIGNMENT_LABELS
from intentfence.route_b import load_route_b_policy

ROOT = Path(__file__).resolve().parents[1]


def validate() -> list[str]:
    errors: list[str] = []
    policy = load_route_b_policy(ROOT / "configs" / "route_b_ai_review_protocol.yaml")
    if policy.get("protocol_version") != "2.1.0-ai-draft.1":
        errors.append("AI review protocol version drifted")
    if policy.get("status") != (
        "ai_review_direction_approved_construction_authorized_not_training_authorized"
    ):
        errors.append("AI review protocol must remain an unfrozen engineering draft")
    if policy.get("evidence_status") != "ai_reviewed_engineering_only":
        errors.append("AI review evidence status drifted")
    if tuple(policy.get("risk_labels", ())) != RISK_LABELS:
        errors.append("AI review Risk labels drifted from canonical labels")
    if tuple(policy.get("task_alignment_labels", ())) != TASK_ALIGNMENT_LABELS:
        errors.append("AI review Alignment labels drifted from canonical labels")
    audit = policy.get("audit", {})
    if audit.get("review_mode") != "dual_ai_engineering":
        errors.append("AI review mode is not dual_ai_engineering")
    if audit.get("independent_human_reviewers_required") != 0:
        errors.append("AI route must not claim an independent human-review requirement")
    if audit.get("independent_ai_reviewers_required") != 2:
        errors.append("AI route must require exactly two AI reviewers")
    if audit.get("ai_review_counts_as_independent_human_review") is not False:
        errors.append("AI review must not be counted as human review")
    if audit.get("distinct_provider_model_revision_required") is not True:
        errors.append("AI reviewer identities must be distinct and versioned")
    if audit.get("temperature_must_equal") != 0:
        errors.append("AI reviewer temperature must be fixed at zero")
    readiness = policy.get("readiness", {})
    if readiness.get("human_verified") is not False:
        errors.append("AI route must keep human_verified=false")
    if readiness.get("formal_training_authorized") is not False:
        errors.append("AI route must keep formal_training_authorized=false")
    if readiness.get("engineering_training_authorized") is not False:
        errors.append("AI route must not authorize engineering training before review")
    for relative in (
        "configs/route_b_ai_review_manifest.example.json",
        "docs/route_b_ai_review_protocol.md",
        "docs/route_b_ai_review_prompt.md",
        "scripts/analyze_route_b_ai_reviews.py",
        "src/intentfence/route_b_ai_review.py",
    ):
        if not (ROOT / relative).is_file():
            errors.append(f"AI review framework file is missing: {relative}")
    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Route B AI review framework validation passed (engineering evidence only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
