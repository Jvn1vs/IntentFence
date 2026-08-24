from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import yaml

from intentfence.constants import RISK_LABELS, TASK_ALIGNMENT_LABELS
from intentfence.mock_runtime import capture_candidate_action
from intentfence.schema import IntentSample

INTERNAL_ROLES = frozenset({"train", "validation", "calibration"})
LOCKED_SOURCE_ROLES = {
    "injecagent": "test_b",
    "notinject": "test_c",
    "agentdojo": "test_d",
}


def load_route_b_policy(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Route B policy must be a mapping: {source}")
    return payload


def _normalized_action_signature(action: str) -> str:
    return re.sub(r"\s+", " ", action.strip().lower())


def validate_route_b_samples(
    samples: Iterable[IntentSample],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    rows = list(samples)
    errors: list[str] = []
    blockers: list[str] = []
    warnings: list[str] = []
    configured_risks = tuple(policy.get("risk_labels", ()))
    configured_alignment = tuple(policy.get("task_alignment_labels", ()))
    if configured_risks != RISK_LABELS:
        errors.append("policy risk_labels do not exactly match the canonical five labels")
    if configured_alignment != TASK_ALIGNMENT_LABELS:
        errors.append(
            "policy task_alignment_labels do not exactly match aligned/unrelated/ambiguous/malicious"
        )
    if not rows:
        errors.append("dataset is empty")

    allowed_provenance = set(
        policy.get("action_evidence", {}).get("allowed_internal_provenance", ())
    )
    by_split: dict[str, list[IntentSample]] = defaultdict(list)
    risk_to_alignment: dict[str, set[str]] = defaultdict(set)
    pair_groups: dict[str, list[IntentSample]] = defaultdict(list)
    template_roles: dict[str, set[str]] = defaultdict(set)
    action_signature_roles: dict[str, set[str]] = defaultdict(set)

    for row in rows:
        split = str(row.split or "unassigned")
        by_split[split].append(row)
        source_key = row.source.casefold().replace("_", "").replace("-", "")
        for locked_source, expected_role in LOCKED_SOURCE_ROLES.items():
            if locked_source in source_key and split != expected_role:
                errors.append(
                    f"{row.sample_id}: locked source {row.source} may only use {expected_role}, got {split}"
                )

        if split in INTERNAL_ROLES:
            if row.task_alignment_label is None:
                errors.append(f"{row.sample_id}: internal Route B row lacks task_alignment_label")
            else:
                risk_to_alignment[row.risk_label].add(row.task_alignment_label)
            if row.action_provenance not in allowed_provenance:
                errors.append(
                    f"{row.sample_id}: internal action_provenance={row.action_provenance!r} is not allowed"
                )
            if not row.action_observation_id:
                errors.append(f"{row.sample_id}: internal row lacks action_observation_id")
            if not row.action_policy_id:
                errors.append(f"{row.sample_id}: internal row lacks action_policy_id")
            pair_group = str(getattr(row, "action_pair_group", "") or "")
            if not pair_group:
                errors.append(f"{row.sample_id}: internal row lacks action_pair_group")
            else:
                pair_groups[pair_group].append(row)

        template_roles[row.template_group].add(split)
        if row.proposed_action:
            action_signature_roles[_normalized_action_signature(row.proposed_action)].add(split)

    for template_group, roles in sorted(template_roles.items()):
        internal = roles & INTERNAL_ROLES
        if len(internal) > 1:
            errors.append(
                f"template_group crosses internal roles: {template_group} -> {sorted(internal)}"
            )
    for signature, roles in sorted(action_signature_roles.items()):
        internal = roles & INTERNAL_ROLES
        if len(internal) > 1:
            errors.append(
                f"normalized action signature crosses internal roles: {signature!r} -> {sorted(internal)}"
            )

    for group, members in sorted(pair_groups.items()):
        base_cases = {
            (row.user_goal, row.untrusted_content, row.risk_label, str(row.split))
            for row in members
        }
        alignments = {row.task_alignment_label for row in members}
        if len(base_cases) != 1:
            errors.append(f"action_pair_group {group!r} does not preserve one base case")
        if len(alignments) < 2:
            errors.append(f"action_pair_group {group!r} lacks contrasting alignment labels")

    internal_rows = [row for row in rows if str(row.split) in INTERNAL_ROLES]
    if internal_rows:
        if not any(
            row.risk_label != "benign" and row.task_alignment_label == "aligned"
            for row in internal_rows
        ):
            errors.append("no non-benign/aligned counterexample; Alignment remains confounded with Risk")
        if not any(
            row.risk_label == "benign"
            and row.task_alignment_label in {"unrelated", "ambiguous"}
            for row in internal_rows
        ):
            errors.append("no benign/non-aligned counterexample; Alignment remains confounded with Risk")
        missing_risks = sorted(set(RISK_LABELS) - {row.risk_label for row in internal_rows})
        missing_alignment = sorted(
            set(TASK_ALIGNMENT_LABELS)
            - {
                row.task_alignment_label
                for row in internal_rows
                if row.task_alignment_label is not None
            }
        )
        if missing_risks:
            blockers.append(f"internal roles lack Risk labels: {missing_risks}")
        if missing_alignment:
            blockers.append(f"internal roles lack task Alignment labels: {missing_alignment}")

    if policy.get("status") != "frozen":
        blockers.append("Route B protocol is not frozen")
    if policy.get("sample_size", {}).get("status") != "frozen":
        blockers.append("sample-size precision/power target is not frozen")
    if not policy.get("readiness", {}).get("formal_training_authorized", False):
        blockers.append("formal_training_authorized is false")

    summary = {
        "rows": len(rows),
        "by_split": {name: len(group) for name, group in sorted(by_split.items())},
        "risk_labels": dict(sorted(Counter(row.risk_label for row in rows).items())),
        "task_alignment_labels": dict(
            sorted(
                Counter(
                    row.task_alignment_label
                    for row in rows
                    if row.task_alignment_label is not None
                ).items()
            )
        ),
        "risk_to_alignment": {
            risk: sorted(labels) for risk, labels in sorted(risk_to_alignment.items())
        },
        "action_pair_groups": len(pair_groups),
    }
    return {
        "status": "failed" if errors else "structure_passed_readiness_blocked" if blockers else "ready",
        "errors": errors,
        "readiness_blockers": blockers,
        "warnings": warnings,
        "summary": summary,
    }


def render_route_b_report(report: Mapping[str, Any]) -> str:
    return json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def wilson_interval(
    successes: int,
    trials: int,
    *,
    z: float = 1.959963984540054,
) -> tuple[float, float]:
    if trials <= 0:
        raise ValueError("trials must be positive")
    if not 0 <= successes <= trials:
        raise ValueError("successes must be between zero and trials")
    proportion = successes / trials
    denominator = 1 + z**2 / trials
    center = (proportion + z**2 / (2 * trials)) / denominator
    half_width = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / trials + z**2 / (4 * trials**2)
        )
        / denominator
    )
    return max(0.0, center - half_width), min(1.0, center + half_width)


def precision_table(
    sample_sizes: Iterable[int],
    *,
    target_rate: float = 0.01,
) -> list[dict[str, float | int]]:
    if not 0 <= target_rate <= 1:
        raise ValueError("target_rate must be between zero and one")
    rows: list[dict[str, float | int]] = []
    for sample_size in sample_sizes:
        if sample_size <= 0:
            raise ValueError("sample sizes must be positive")
        events = round(target_rate * sample_size)
        lower, upper = wilson_interval(events, sample_size)
        rows.append(
            {
                "sample_size": sample_size,
                "events_nearest_target": events,
                "empirical_rate": events / sample_size,
                "one_event_resolution": 1 / sample_size,
                "wilson_95_lower": lower,
                "wilson_95_upper": upper,
                "wilson_95_half_width": (upper - lower) / 2,
            }
        )
    return rows


def build_mock_catalog_records(
    catalog: Mapping[str, Any],
) -> tuple[list[IntentSample], list[dict[str, Any]]]:
    if catalog.get("status") != "framework_fixture_not_training_data":
        raise ValueError("only explicitly marked framework fixtures may use this builder")
    policy_id = str(catalog.get("action_policy_id", ""))
    cases = catalog.get("cases")
    if not policy_id or not isinstance(cases, list) or not cases:
        raise ValueError("catalog requires action_policy_id and a non-empty cases list")
    records: list[IntentSample] = []
    traces: list[dict[str, Any]] = []
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("every catalog case must be a mapping")
        case_id = str(case["case_id"])
        candidates = case.get("candidates")
        if not isinstance(candidates, list) or len(candidates) < 2:
            raise ValueError(f"{case_id}: at least two contrasting action candidates are required")
        for index, candidate in enumerate(candidates):
            if not isinstance(candidate, dict):
                raise ValueError(f"{case_id}: action candidate must be a mapping")
            action, trace = capture_candidate_action(
                case_id=case_id,
                policy_id=policy_id,
                tool=str(candidate["tool"]),
                arguments=candidate.get("arguments", {}),
                field_provenance=candidate.get("field_provenance", {}),
            )
            alignment = str(candidate["task_alignment_label"])
            risk = str(case["risk_label"])
            records.append(
                IntentSample(
                    sample_id=f"{case_id}-action-{index}",
                    source=str(catalog.get("source", "IntentFenceMockFixture")),
                    scenario=str(case["scenario"]),
                    user_goal=str(case["user_goal"]),
                    untrusted_content=str(case["untrusted_content"]),
                    proposed_action=action,
                    risk_label=risk,
                    alignment_label=int(risk != "benign"),
                    task_alignment_label=alignment,
                    attack_family=str(case.get("attack_family", "none")),
                    severity=int(case.get("severity", 0)),
                    template_group=str(case["template_group"]),
                    split=str(case["split"]),
                    adapter_profile="route_b_mock_fixture_v1",
                    adapter_missing_action=False,
                    action_provenance="sandbox_policy_output",
                    action_observation_id=trace["action_observation_id"],
                    action_policy_id=policy_id,
                    field_provenance=candidate.get("field_provenance", {}),
                    action_pair_group=case_id,
                    scenario_family=str(case["scenario_family"]),
                )
            )
            traces.append(trace)
    return records, traces
