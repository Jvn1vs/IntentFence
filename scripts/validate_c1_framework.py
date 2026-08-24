from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from _prepare import PROFILES
from download_sources import C1_SOURCES, build_plan
from summarize_label_audit import (
    AUDIT_REQUIRED_GROUPING,
    AUDIT_SELECTION_ALGORITHM,
    AUDIT_SELECTION_ALGORITHM_VERSION,
    AUDIT_SELECTION_SEED,
)

from intentfence.data import C1_REQUIRED_SPLITS

ROOT = Path(__file__).resolve().parents[1]
SHA40 = re.compile(r"^[0-9a-f]{40}$")


def _yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a mapping")
    return value


def validate() -> list[str]:
    errors: list[str] = []
    pipeline = _yaml(ROOT / "configs" / "data_pipeline.yaml")
    registry = _yaml(ROOT / "configs" / "experiment_registry.yaml")
    upstream = _yaml(ROOT / "configs" / "upstream_sources.yaml")
    execution = _yaml(ROOT / "configs" / "execution_policy.yaml")
    baseline_sources = _yaml(ROOT / "configs" / "baseline_sources.yaml")

    if pipeline.get("execution_owner") != "project_owner":
        errors.append("C1 data execution owner must be project_owner")
    if pipeline.get("execution_operator") != "codex_or_project_owner":
        errors.append("C1 data execution operator must allow Codex or project owner")
    allowed = set(pipeline.get("codex_allowed_operations", []))
    required_allowed = {
        "download_preapproved_pinned_sources",
        "convert_merge_deduplicate_and_split_real_project_data",
        "inspect_and_pre_review_labels_with_truthful_reviewer_provenance",
        "generate_data_quality_and_reproducibility_reports",
    }
    if not required_allowed.issubset(allowed):
        errors.append("C1 Codex data permissions are incomplete")
    prohibited = set(pipeline.get("codex_prohibited_operations", []))
    required = {
        "fit_any_model_on_real_project_data",
        "update_model_or_calibration_parameters",
        "access_formal_final_test_model_results_before_freeze",
        "claim_ai_review_as_independent_human_review",
        "apply_ai_only_review_as_human_verified",
    }
    if not required.issubset(prohibited):
        errors.append("C1 Codex training/test/reviewer prohibitions are incomplete")
    if registry.get("status") != "frozen":
        errors.append("C1 cannot start from an unfrozen research protocol")
    if registry.get("resources", {}).get("training_executor") != "project_owner_only":
        errors.append("training executor drifted from project_owner_only")
    if execution.get("owner") != "project_owner":
        errors.append("execution policy owner must be project_owner")
    execution_allowed = set(execution.get("codex_allowed", []))
    if not {
        "execute_preapproved_pinned_source_downloads",
        "convert_merge_deduplicate_and_split_real_project_data",
        "inspect_and_pre_review_real_project_data_with_truthful_reviewer_provenance",
        "generate_data_quality_integrity_and_reproducibility_reports",
    }.issubset(execution_allowed):
        errors.append("machine-readable Codex data permissions are incomplete")
    execution_prohibited = set(execution.get("codex_prohibited", []))
    if not {
        "fit_tfidf_or_any_other_learned_baseline_on_real_project_data",
        "run_small_or_base_model_training_or_tiny_overfit",
        "update_model_or_calibration_parameters",
        "claim_codex_label_review_as_independent_human_verification",
        "apply_codex_only_review_as_human_verified",
    }.issubset(execution_prohibited):
        errors.append("machine-readable Codex execution prohibitions are incomplete")

    configured_profiles = {
        profile
        for source in pipeline.get("sources", {}).values()
        for profile in source.get("adapter_profiles", [])
    }
    if configured_profiles != set(PROFILES):
        errors.append("configured adapter profiles do not exactly match implemented profiles")
    if pipeline.get("bipia_builder") != {
        "task": "email",
        "seed": 42,
        "contexts": "benchmark/email/train.jsonl",
        "attacks": "benchmark/text_attack_train.json",
    }:
        errors.append("BIPIA builder contract drifted from the frozen C1 route")
    if pipeline.get("conversion_inputs") != {
        "bipia_clean_v1": {
            "source": "bipia",
            "paths": ["benchmark/email/train.jsonl"],
        },
        "injecagent_direct_harm_v1": {
            "source": "injecagent",
            "paths": ["data/test_cases_dh_base.json"],
        },
        "injecagent_data_stealing_v1": {
            "source": "injecagent",
            "paths": ["data/test_cases_ds_base.json"],
        },
        "notinject_v1": {
            "source": "notinject",
            "paths": [
                "data/NotInject_one-00000-of-00001.parquet",
                "data/NotInject_two-00000-of-00001.parquet",
                "data/NotInject_three-00000-of-00001.parquet",
            ],
        },
    }:
        errors.append("conversion input contract drifted from the frozen C1 route")
    audit_contract = pipeline.get("audit")
    if not isinstance(audit_contract, dict):
        errors.append("audit sampling contract is missing")
    else:
        if audit_contract.get("seed") != AUDIT_SELECTION_SEED:
            errors.append("audit sampling seed drifted from the frozen C1 route")
        if audit_contract.get("selection_algorithm") != AUDIT_SELECTION_ALGORITHM:
            errors.append("audit selection algorithm drifted from the frozen C1 route")
        if (
            audit_contract.get("selection_algorithm_version")
            != AUDIT_SELECTION_ALGORITHM_VERSION
        ):
            errors.append("audit selection algorithm version drifted from the frozen C1 route")
        if audit_contract.get("required_grouping") != list(AUDIT_REQUIRED_GROUPING):
            errors.append("audit required grouping drifted from the frozen C1 route")

    expected_action_policy = {
        "train": ({"BIPIA"}, set(), "blocked_pending_approved_action_audit"),
        "validation": ({"BIPIA"}, set(), "blocked_pending_approved_action_audit"),
        "calibration": ({"BIPIA"}, set(), "blocked_pending_approved_action_audit"),
        "test_a": ({"BIPIA"}, set(), "blocked_pending_approved_action_audit"),
        "test_b": (
            {"InjecAgent"},
            {"benchmark_target"},
            "benchmark_target_not_observed_agent_output",
        ),
        "test_c": (
            {"NotInject"},
            {"protocol_wrapper"},
            "protocol_wrapper_for_overdefense_only",
        ),
    }
    action_policy = pipeline.get("action_evidence_policy")
    if not isinstance(action_policy, dict) or set(action_policy) != set(C1_REQUIRED_SPLITS):
        errors.append("action evidence policy must define exactly the six C1 split roles")
    else:
        for split, (sources, provenance, scope) in expected_action_policy.items():
            entry = action_policy.get(split)
            if not isinstance(entry, dict):
                errors.append(f"action evidence policy entry is invalid: {split}")
                continue
            configured_sources = set(entry.get("sources", []))
            configured_provenance = set(entry.get("allowed_provenance", []))
            if configured_sources != sources:
                errors.append(f"action evidence sources drifted for {split}")
            if configured_provenance != provenance:
                errors.append(f"action evidence provenance drifted for {split}")
            if {"missing", "unknown"} & configured_provenance:
                errors.append(f"invalid action provenance is allowed for {split}")
            if entry.get("evidence_scope") != scope:
                errors.append(f"action evidence scope drifted for {split}")
    if pipeline.get("quality_gates", {}).get("action_mode_invalid_provenance_rows") != 0:
        errors.append("action-mode invalid provenance quality gate must be zero")

    for name, model in baseline_sources.get("models", {}).items():
        if not SHA40.fullmatch(model.get("revision", "")):
            errors.append(f"external baseline {name} lacks a full immutable model revision")

    source_entries = upstream.get("sources", {})
    for item in build_plan(list(C1_SOURCES), ROOT / "data" / "raw"):
        if not SHA40.fullmatch(item["revision"]):
            errors.append(f"{item['name']} does not use a full immutable revision")
        if item["name"] not in source_entries:
            errors.append(f"{item['name']} is absent from upstream registry")

    for relative in (
        "scripts/download_sources.py",
        "scripts/prepare_bipia.py",
        "scripts/prepare_injecagent.py",
        "scripts/prepare_notinject.py",
        "scripts/export_bipia_builder.py",
        "scripts/merge_canonical.py",
        "scripts/build_splits.py",
        "scripts/validate_dataset.py",
        "scripts/build_dataset_reports.py",
        "scripts/audit_labels.py",
        "scripts/summarize_label_audit.py",
        "scripts/apply_label_audit.py",
        "baselines/predict.py",
        "baselines/evaluate_scores.py",
        "baselines/aggregate_results.py",
    ):
        if not (ROOT / relative).is_file():
            errors.append(f"required C1 framework file is missing: {relative}")
    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("C1 framework validation passed (no real data executed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
