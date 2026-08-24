from __future__ import annotations

from pathlib import Path

from intentfence.constants import RISK_LABELS, TASK_ALIGNMENT_LABELS
from intentfence.route_b import load_route_b_policy

ROOT = Path(__file__).resolve().parents[1]


def validate() -> list[str]:
    errors: list[str] = []
    policy = load_route_b_policy(ROOT / "configs" / "route_b_data_protocol.yaml")
    if tuple(policy.get("risk_labels", ())) != RISK_LABELS:
        errors.append("Route B risk label registry drifted from canonical labels")
    if tuple(policy.get("task_alignment_labels", ())) != TASK_ALIGNMENT_LABELS:
        errors.append("Route B task alignment registry drifted from canonical labels")
    if policy.get("status") != "direction_approved_construction_authorized_not_frozen":
        errors.append("Route B direction approval or unfrozen construction status drifted")
    if policy.get("project_owned_mock_corpus_authorized") is not True:
        errors.append("Route B project-owned mock corpus construction is not authorized")
    if policy.get("unapproved_cc_by_sa_and_noncommercial_sources_excluded") is not True:
        errors.append("Route B unapproved external-source exclusion drifted")
    if policy.get("readiness", {}).get("formal_training_authorized") is not False:
        errors.append("Route B framework stage must not authorize training")
    if policy.get("audit", {}).get("independent_human_reviewers_required") != 2:
        errors.append("Route B must require two independent human review streams")
    prohibited = set(
        policy.get("action_evidence", {}).get("prohibited_internal_provenance", ())
    )
    if not {"benchmark_target", "protocol_wrapper", "missing", "unknown"}.issubset(
        prohibited
    ):
        errors.append("Route B internal action provenance policy is not fail-closed")
    for relative in (
        "docs/route_b_data_protocol.md",
        "docs/route_b_user_runbook.md",
        "scripts/build_route_b_mock_fixture.py",
        "scripts/build_route_b_mock_corpus.py",
        "scripts/build_route_b_blind_audits.py",
        "scripts/analyze_route_b_blind_audits.py",
        "scripts/plan_route_b_precision.py",
        "scripts/validate_route_b_dataset.py",
        "scripts/validate_route_b_manifest.py",
        "tests/fixtures/route_b_mock_catalog.yaml",
        "configs/route_b_mock_corpus.yaml",
        "docs/route_b_audit_rubric.md",
    ):
        if not (ROOT / relative).is_file():
            errors.append(f"Route B framework file is missing: {relative}")
    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Route B framework validation passed (construction authorized; training blocked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
