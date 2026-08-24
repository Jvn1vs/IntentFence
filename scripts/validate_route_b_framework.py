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
    if policy.get("status") != "draft_unfrozen_not_training_authorized":
        errors.append("Route B draft must remain explicitly unfrozen")
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
        "scripts/plan_route_b_precision.py",
        "scripts/validate_route_b_dataset.py",
        "tests/fixtures/route_b_mock_catalog.yaml",
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
    print("Route B framework validation passed (draft remains training-blocked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
