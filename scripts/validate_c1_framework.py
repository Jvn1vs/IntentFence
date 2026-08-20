from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from _prepare import PROFILES
from download_sources import C1_SOURCES, build_plan

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
    prohibited = set(pipeline.get("codex_prohibited_operations", []))
    required = {
        "download_real_training_or_test_data",
        "convert_or_merge_real_project_data",
        "fit_any_model_on_real_project_data",
        "run_final_data_audit_for_the_owner",
    }
    if not required.issubset(prohibited):
        errors.append("C1 Codex data/training prohibitions are incomplete")
    if registry.get("status") != "frozen":
        errors.append("C1 cannot start from an unfrozen research protocol")
    if registry.get("resources", {}).get("training_executor") != "project_owner_only":
        errors.append("training executor drifted from project_owner_only")
    if execution.get("owner") != "project_owner":
        errors.append("execution policy owner must be project_owner")
    execution_prohibited = set(execution.get("codex_prohibited", []))
    if not {
        "download_real_project_datasets",
        "convert_merge_deduplicate_split_or_audit_real_project_data",
        "fit_tfidf_or_any_other_learned_baseline_on_real_project_data",
        "run_small_or_base_model_training_or_tiny_overfit",
    }.issubset(execution_prohibited):
        errors.append("machine-readable Codex execution prohibitions are incomplete")

    configured_profiles = {
        profile
        for source in pipeline.get("sources", {}).values()
        for profile in source.get("adapter_profiles", [])
    }
    if configured_profiles != set(PROFILES):
        errors.append("configured adapter profiles do not exactly match implemented profiles")

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
        "scripts/audit_labels.py",
        "scripts/summarize_label_audit.py",
        "scripts/apply_label_audit.py",
        "baselines/predict.py",
        "baselines/evaluate_scores.py",
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
