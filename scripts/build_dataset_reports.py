from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import yaml
from _prepare import convert_records
from apply_label_audit import apply_audit
from summarize_label_audit import (
    AUDIT_REQUIRED_GROUPING,
    AUDIT_SELECTION_ALGORITHM,
    AUDIT_SELECTION_ALGORITHM_VERSION,
    AUDIT_SELECTION_SEED,
    summarize,
    validate_audit_key,
)

from intentfence.constants import RISK_LABELS
from intentfence.data import (
    C1_REQUIRED_SPLITS,
    audit_split_manifest,
    dataset_summary,
    deduplicate_samples,
    group_aware_split,
)
from intentfence.schema import IntentSample, read_jsonl

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs" / "data_pipeline.yaml"
DEFAULT_SOURCE_REGISTRY = ROOT / "configs" / "upstream_sources.yaml"
EXPECTED_CONVERSION_PROFILES = Counter(
    {
        "bipia_generated_v1": 1,
        "bipia_clean_v1": 1,
        "injecagent_direct_harm_v1": 1,
        "injecagent_data_stealing_v1": 1,
        "notinject_v1": 3,
    }
)
EXPECTED_SOURCES = {"bipia", "injecagent", "notinject"}
EXPECTED_CONVERSION_METADATA = {
    "bipia_generated_v1": {
        "source": "BIPIA",
        "split": None,
        "action_provenance": "missing",
        "risk_label": "instruction_hijacking",
    },
    "bipia_clean_v1": {
        "source": "BIPIA",
        "split": None,
        "action_provenance": "missing",
        "risk_label": "benign",
    },
    "injecagent_direct_harm_v1": {
        "source": "InjecAgent",
        "split": "test_b",
        "action_provenance": "benchmark_target",
        "risk_label": "tool_manipulation",
    },
    "injecagent_data_stealing_v1": {
        "source": "InjecAgent",
        "split": "test_b",
        "action_provenance": "benchmark_target",
        "risk_label": "data_exfiltration",
    },
    "notinject_v1": {
        "source": "NotInject",
        "split": "test_c",
        "action_provenance": "protocol_wrapper",
        "risk_label": "benign",
    },
}


def _input_spec(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("input must be SPLIT=PATH")
    split, raw_path = value.split("=", maxsplit=1)
    return split, Path(raw_path)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read JSON evidence {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JSON evidence must contain an object: {path}")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_project_path(raw_path: str | Path) -> Path:
    path = Path(raw_path)
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def _artifact_files(target: Path) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for path in sorted(target.rglob("*")):
        if (
            not path.is_file()
            or path.suffix in {".pyc", ".pyo"}
            or any(part in {".git", ".cache", "__pycache__"} for part in path.parts)
        ):
            continue
        files.append(
            {
                "path": path.relative_to(target).as_posix(),
                "size": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    return files


def _load_pipeline_contract(config_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    resolved_config = _resolve_project_path(config_path)
    if resolved_config != DEFAULT_CONFIG.resolve():
        raise ValueError(f"C1 reports require the canonical config: {DEFAULT_CONFIG}")
    config = yaml.safe_load(resolved_config.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError(f"C1 data config is invalid: {config_path}")
    raw_registry = config.get("source_registry")
    if not isinstance(raw_registry, str):
        raise ValueError("C1 data config source_registry is missing")
    registry_path = _resolve_project_path(raw_registry)
    if registry_path != DEFAULT_SOURCE_REGISTRY.resolve():
        raise ValueError(f"C1 reports require the canonical source registry: {DEFAULT_SOURCE_REGISTRY}")
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    if not isinstance(registry, dict) or not isinstance(registry.get("sources"), dict):
        raise ValueError(f"Source registry is invalid: {registry_path}")
    return config, registry["sources"]


def compute_label_statistics(
    samples_by_split: dict[str, list[IntentSample]],
    action_policy: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    records = [row for split in C1_REQUIRED_SPLITS for row in samples_by_split[split]]
    relationship_records = samples_by_split["train"]
    contingency = {
        label: {
            "0": sum(
                row.risk_label == label and row.alignment_label == 0
                for row in relationship_records
            ),
            "1": sum(
                row.risk_label == label and row.alignment_label == 1
                for row in relationship_records
            ),
        }
        for label in RISK_LABELS
    }
    relationship_total = len(relationship_records)
    risk_totals = {label: sum(contingency[label].values()) for label in RISK_LABELS}
    alignment_totals = {
        alignment: sum(contingency[label][alignment] for label in RISK_LABELS)
        for alignment in ("0", "1")
    }
    alignment_given_risk = {
        label: {
            alignment: (
                contingency[label][alignment] / risk_totals[label]
                if risk_totals[label]
                else None
            )
            for alignment in ("0", "1")
        }
        for label in RISK_LABELS
    }
    risk_given_alignment = {
        alignment: {
            label: (
                contingency[label][alignment] / alignment_totals[alignment]
                if alignment_totals[alignment]
                else None
            )
            for label in RISK_LABELS
        }
        for alignment in ("0", "1")
    }
    mutual_information_nats = 0.0
    if relationship_total:
        for label in RISK_LABELS:
            for alignment in ("0", "1"):
                joint_count = contingency[label][alignment]
                if not joint_count:
                    continue
                joint = joint_count / relationship_total
                risk_probability = risk_totals[label] / relationship_total
                alignment_probability = alignment_totals[alignment] / relationship_total
                mutual_information_nats += joint * math.log(
                    joint / (risk_probability * alignment_probability)
                )
    mutual_information_bits = (
        mutual_information_nats / math.log(2) if relationship_total else 0.0
    )
    alignment_entropy_bits = -sum(
        probability * math.log2(probability)
        for count in alignment_totals.values()
        if (probability := count / relationship_total if relationship_total else 0.0) > 0
    )
    deterministic = all(
        sum(contingency[label][alignment] > 0 for alignment in ("0", "1")) <= 1
        for label in RISK_LABELS
    )

    by_split = {}
    for split in C1_REQUIRED_SPLITS:
        summary = dataset_summary(samples_by_split[split])
        summary["action_provenance"] = dict(
            sorted(Counter(row.action_provenance for row in samples_by_split[split]).items())
        )
        by_split[split] = summary
    train_labels = set(by_split["train"]["risk_labels"])
    missing_train_labels = sorted(set(RISK_LABELS) - train_labels)
    binary_attack_train_class_coverage_present = "benign" in train_labels and bool(
        train_labels - {"benign"}
    )
    role_coverage = {}
    for split in ("train", "validation", "calibration"):
        labels = set(by_split[split]["risk_labels"])
        role_coverage[split] = {
            "present_risk_labels": sorted(labels),
            "missing_risk_labels": sorted(set(RISK_LABELS) - labels),
            "binary_benign_and_attack_present": "benign" in labels
            and bool(labels - {"benign"}),
        }

    action_blockers: dict[str, list[str]] = {}
    for split in ("train", "validation", "calibration", "test_a"):
        policy = action_policy.get(split, {})
        allowed_sources = set(policy.get("sources", []))
        allowed_provenance = set(policy.get("allowed_provenance", []))
        blockers: list[str] = []
        if not allowed_provenance:
            blockers.append("no approved action provenance")
        invalid_rows = sum(
            not row.proposed_action
            or row.adapter_missing_action
            or row.source not in allowed_sources
            or row.action_provenance not in allowed_provenance
            for row in samples_by_split[split]
        )
        if invalid_rows:
            blockers.append(f"{invalid_rows} rows lack policy-approved action evidence")
        if blockers:
            action_blockers[split] = blockers

    return {
        "schema_version": 1,
        "total_rows": len(records),
        "by_split": by_split,
        "risk_alignment": {
            "scope": "train_only",
            "rows": relationship_total,
            "contingency": contingency,
            "alignment_given_risk": alignment_given_risk,
            "risk_given_alignment": risk_given_alignment,
            "mutual_information_nats": mutual_information_nats,
            "mutual_information_bits": mutual_information_bits,
            "alignment_entropy_bits": alignment_entropy_bits,
            "mi_fraction_of_alignment_entropy": (
                mutual_information_bits / alignment_entropy_bits
                if alignment_entropy_bits > 0
                else None
            ),
            "alignment_is_deterministic_from_risk": deterministic,
        },
        "training_readiness": {
            "assessment_scope": (
                "class_presence_and_action_evidence_only_not_formal_training_authorization"
            ),
            "binary_attack_train_class_coverage_present": (
                binary_attack_train_class_coverage_present
            ),
            "five_class_train_class_coverage_present": not missing_train_labels,
            "missing_train_risk_labels": missing_train_labels,
            "risk_class_coverage_by_training_role": role_coverage,
            "minimum_per_class_support_not_assessed": True,
            "alignment_auxiliary_target_has_independent_label_information": not deterministic,
            "model_c_action_data_ready": not action_blockers,
            "model_c_action_blockers": action_blockers,
            "formal_training_authorized": False,
            "formal_training_blocker": (
                "project_owner_protocol_and_action-route_decision_is_pending"
            ),
        },
    }


def _sample_signature(sample: IntentSample, *, ignore_split: bool = False) -> str:
    payload = sample.model_dump(mode="json")
    if ignore_split:
        payload.pop("split", None)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _validate_conversion_replay(
    *,
    report_path: Path,
    report: dict[str, Any],
    profile: str,
    pipeline_config: dict[str, Any],
    canonical_rows: list[IntentSample],
) -> list[str]:
    """Re-run the pinned adapter and bind canonical rows to their recorded input."""

    errors: list[str] = []
    raw_input = report.get("input")
    if not isinstance(raw_input, str):
        return [f"conversion input is unavailable for deterministic replay: {report_path}"]
    input_path = _resolve_project_path(raw_input)
    if not input_path.is_file():
        return [f"conversion input is unavailable for deterministic replay: {report_path}"]

    scenario_override = None
    if profile == "bipia_clean_v1":
        builder_contract = pipeline_config.get("bipia_builder")
        task = builder_contract.get("task") if isinstance(builder_contract, dict) else None
        if not isinstance(task, str) or not task:
            return ["BIPIA clean conversion replay lacks the frozen task name"]
        scenario_override = task
    expected_metadata = EXPECTED_CONVERSION_METADATA.get(profile)
    if expected_metadata is None:
        return [f"conversion profile cannot be replayed: {profile}"]

    try:
        replayed_rows, replayed_skips, records_read = convert_records(
            input_path,
            profile_name=profile,
            scenario_override=scenario_override,
            split_override=expected_metadata["split"],
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return [f"cannot replay conversion {report_path}: {exc}"]

    if report.get("records_read") != records_read:
        errors.append(f"conversion records_read does not match adapter replay: {report_path}")
    if report.get("converted") != len(replayed_rows):
        errors.append(f"conversion converted count does not match adapter replay: {report_path}")
    if report.get("skipped") != len(replayed_skips):
        errors.append(f"conversion skipped count does not match adapter replay: {report_path}")
    if report.get("skipped_records") != replayed_skips[:100]:
        errors.append(f"conversion skipped records do not match adapter replay: {report_path}")
    if [_sample_signature(row) for row in canonical_rows] != [
        _sample_signature(row) for row in replayed_rows
    ]:
        errors.append(
            f"conversion canonical rows do not match deterministic adapter replay: {report_path}"
        )
    return errors


def _validate_audit_replay(
    *,
    pipeline_config: dict[str, Any],
    audit_key: dict[str, Any],
    audit_key_path: Path,
    audit_summary: dict[str, Any],
    audit_application: dict[str, Any],
    audit_sheet: Path | None,
    merge_output: Path | None,
    merge_rows: list[IntentSample] | None,
    audited_output: Path | None,
    effective_minimum: int,
) -> list[str]:
    """Replay the sealed audit selection, summary, and application from canonical input."""

    errors: list[str] = []
    audit_contract = pipeline_config.get("audit")
    if not isinstance(audit_contract, dict):
        errors.append("pipeline audit contract is missing for audit replay")
    else:
        frozen_fields = {
            "seed": AUDIT_SELECTION_SEED,
            "selection_algorithm": AUDIT_SELECTION_ALGORITHM,
            "selection_algorithm_version": AUDIT_SELECTION_ALGORITHM_VERSION,
            "required_grouping": list(AUDIT_REQUIRED_GROUPING),
        }
        for field, expected in frozen_fields.items():
            if audit_contract.get(field) != expected:
                errors.append(f"pipeline audit {field} does not match the frozen replay contract")

    if (
        audit_sheet is None
        or not audit_sheet.is_file()
        or merge_output is None
        or merge_rows is None
        or audited_output is None
        or not audited_output.is_file()
    ):
        errors.append("audit artifacts are unavailable for deterministic replay")
        return errors

    try:
        with audit_sheet.open(encoding="utf-8-sig", newline="") as handle:
            audit_rows = list(csv.DictReader(handle))
    except OSError as exc:
        errors.append(f"cannot read audit sheet for replay: {exc}")
        return errors

    replayed_key, key_errors = validate_audit_key(
        audit_key_path,
        audit_sheet,
        audit_rows,
        expected_input=merge_output,
    )
    errors.extend(f"audit key replay: {error}" for error in key_errors)
    if replayed_key != audit_key:
        errors.append("loaded audit key does not match the key used for replay")

    replayed_summary = summarize(audit_rows, effective_minimum)
    for field, expected in replayed_summary.items():
        if audit_summary.get(field) != expected:
            errors.append(f"audit summary {field} does not match deterministic replay")
        if audit_application.get(field) != expected:
            errors.append(f"audit application {field} does not match deterministic replay")

    if key_errors or replayed_summary.get("errors"):
        return errors
    try:
        replayed_output, replayed_application = apply_audit(
            merge_rows,
            audit_rows,
            effective_minimum,
        )
    except (TypeError, ValueError) as exc:
        errors.append(f"cannot replay audit application: {exc}")
        return errors
    if audit_application.get("application_counts") != replayed_application.get(
        "application_counts"
    ):
        errors.append("audit application counts do not match deterministic replay")
    actual_audited_rows = read_jsonl(audited_output)
    if [_sample_signature(row) for row in actual_audited_rows] != [
        _sample_signature(row) for row in replayed_output
    ]:
        errors.append("audited output rows do not match deterministic audit application replay")
    return errors


def _validate_split_lineage(
    *,
    samples_by_split: dict[str, list[IntentSample]],
    conversion_reports: list[tuple[Path, dict[str, Any]]],
    audit_application: dict[str, Any],
    pipeline_config: dict[str, Any],
    split_manifest: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    raw_audited_output = audit_application.get("output")
    if not isinstance(raw_audited_output, str):
        return ["audit application output path is missing for split-lineage validation"]
    audited_rows = read_jsonl(_resolve_project_path(raw_audited_output))
    primary_roles = ("train", "validation", "calibration", "test_a")
    split_contract = pipeline_config.get("split")
    replayed_manifest: dict[str, Any] | None = None
    deduplication = None
    if not isinstance(split_contract, dict):
        errors.append("pipeline split contract is missing for split-lineage replay")
    else:
        seed = split_contract.get("seed")
        ratios = split_contract.get("ratios")
        near_threshold = split_contract.get("near_duplicate_threshold")
        valid_ratios = (
            isinstance(ratios, dict)
            and set(ratios) == set(primary_roles)
            and all(
                isinstance(value, int | float)
                and not isinstance(value, bool)
                and value > 0
                for value in ratios.values()
            )
        )
        if (
            type(seed) is not int
            or not valid_ratios
            or not isinstance(near_threshold, int | float)
            or isinstance(near_threshold, bool)
            or not 0 < near_threshold <= 1
        ):
            errors.append("pipeline split replay parameters are invalid")
        else:
            try:
                deduplication = deduplicate_samples(
                    audited_rows, near_threshold=float(near_threshold)
                )
                replayed_rows, replayed_manifest = group_aware_split(
                    deduplication.kept,
                    ratios={str(key): float(value) for key, value in ratios.items()},
                    seed=seed,
                )
            except (TypeError, ValueError) as exc:
                errors.append(f"cannot replay primary split lineage: {exc}")
            else:
                for split in primary_roles:
                    expected = Counter(
                        _sample_signature(row)
                        for row in replayed_rows
                        if row.split == split
                    )
                    actual = Counter(
                        _sample_signature(row) for row in samples_by_split[split]
                    )
                    if actual != expected:
                        errors.append(
                            f"{split} does not exactly match the replayed deterministic split"
                        )

    manifest_deduplication = split_manifest.get("deduplication")
    if deduplication is not None:
        expected_deduplication = {
            "kept": len(deduplication.kept),
            "exact_duplicates": [list(item) for item in deduplication.exact_duplicates],
            "near_duplicates": [list(item) for item in deduplication.near_duplicates],
            "near_threshold": split_contract["near_duplicate_threshold"],
        }
        if not isinstance(manifest_deduplication, dict):
            errors.append("split manifest deduplication evidence is missing")
        else:
            for field, expected in expected_deduplication.items():
                if manifest_deduplication.get(field) != expected:
                    errors.append(
                        f"split manifest deduplication {field} does not match replay"
                    )
    if replayed_manifest is not None and split_manifest.get(
        "group_to_split"
    ) != replayed_manifest.get("group_to_split"):
        errors.append("split manifest group_to_split does not match replay")

    primary_input = split_manifest.get("primary_input")
    if not isinstance(primary_input, dict) or primary_input.get("rows") != len(audited_rows):
        errors.append("split manifest primary input row count does not match audited output")

    external_rows_by_split: dict[str, list[IntentSample]] = {}
    for split in ("test_b", "test_c"):
        expected_rows: list[IntentSample] = []
        for _, report in conversion_reports:
            if report.get("split") != split or not isinstance(report.get("output"), str):
                continue
            expected_rows.extend(read_jsonl(_resolve_project_path(report["output"])))
        external_rows_by_split[split] = expected_rows
        expected = Counter(_sample_signature(row) for row in expected_rows)
        actual = Counter(_sample_signature(row) for row in samples_by_split[split])
        if actual != expected:
            errors.append(
                f"{split} does not exactly equal its sealed external conversion outputs"
            )

    if replayed_manifest is not None:
        expected_counts = dict(replayed_manifest.get("counts", {}))
        for split, rows in external_rows_by_split.items():
            expected_counts[split] = {
                "total": len(rows),
                "by_risk": dataset_summary(rows)["risk_labels"],
            }
        if split_manifest.get("counts") != expected_counts:
            errors.append("split manifest counts do not match replayed role counts")
    return errors


def _validate_evidence(
    *,
    source_manifest: dict[str, Any],
    source_manifest_path: Path,
    source_registry: dict[str, Any],
    pipeline_config: dict[str, Any],
    builder_report: dict[str, Any],
    conversion_reports: list[tuple[Path, dict[str, Any]]],
    merge_report: dict[str, Any],
    audit_key: dict[str, Any],
    audit_key_path: Path,
    audit_summary: dict[str, Any],
    audit_application: dict[str, Any],
    split_manifest: dict[str, Any],
    split_manifest_path: Path,
    context_integrity: dict[str, Any],
    external_action_integrity: dict[str, Any],
    minimum_audit_rows: int,
) -> list[str]:
    errors: list[str] = []
    source_artifacts: dict[str, dict[Path, tuple[int, str]]] = {}
    source_targets: dict[str, Path] = {}
    source_rows = source_manifest.get("sources")
    if not isinstance(source_rows, list):
        errors.append("source manifest sources list is missing")
    else:
        raw_names = [
            row["name"]
            for row in source_rows
            if isinstance(row, dict) and isinstance(row.get("name"), str)
        ]
        names = set(raw_names)
        if names != EXPECTED_SOURCES:
            errors.append(
                f"source manifest must contain exactly {sorted(EXPECTED_SOURCES)}; got {sorted(names)}"
            )
        if len(raw_names) != len(names):
            errors.append("source manifest contains duplicate source names")
        for row in source_rows:
            if not isinstance(row, dict):
                errors.append("source manifest contains an invalid source entry")
                continue
            name = row.get("name")
            frozen = source_registry.get(name) if isinstance(name, str) else None
            if not isinstance(frozen, dict):
                errors.append(f"source is not present in the frozen registry: {name}")
                continue
            for manifest_field, registry_field in (
                ("revision", "revision"),
                ("official_url", "official_url"),
                ("license_finding", "license"),
            ):
                if row.get(manifest_field) != frozen.get(registry_field):
                    errors.append(
                        f"source {manifest_field} does not match the frozen registry: {name}"
                    )
            expected_method = (
                "huggingface_snapshot"
                if frozen.get("kind") == "huggingface_dataset"
                else "git"
            )
            if row.get("method") != expected_method:
                errors.append(f"source retrieval method does not match registry: {name}")
            if row.get("retrieval_status") not in {"downloaded", "reused_verified"}:
                errors.append(f"source retrieval status is invalid: {name}")
            files = row.get("files")
            if not isinstance(files, list) or not files:
                errors.append(f"source file inventory is missing: {name}")
                continue
            raw_target = row.get("target")
            if not isinstance(raw_target, str):
                errors.append(f"source target is missing: {name}")
                continue
            target = _resolve_project_path(raw_target)
            if not target.is_dir():
                errors.append(f"source target is missing: {target}")
                continue
            source_artifacts[str(name)] = {}
            source_targets[str(name)] = target
            for entry in files:
                if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                    errors.append(f"source file inventory entry is invalid: {name}")
                    continue
                artifact = (target / entry["path"]).resolve()
                if target not in artifact.parents:
                    errors.append(f"source file path escapes its target: {artifact}")
                    continue
                expected_size = entry.get("size")
                expected_hash = entry.get("sha256")
                if type(expected_size) is int and isinstance(expected_hash, str):
                    source_artifacts[str(name)][artifact] = (expected_size, expected_hash)
                if not artifact.is_file():
                    errors.append(f"source file is missing: {artifact}")
                elif type(expected_size) is not int or artifact.stat().st_size != expected_size:
                    errors.append(f"source file size mismatch: {artifact}")
                elif not isinstance(expected_hash, str) or _sha256(artifact) != expected_hash:
                    errors.append(f"source file hash mismatch: {artifact}")
            if files != _artifact_files(target):
                errors.append(f"source inventory does not exactly match the snapshot: {name}")
    if source_manifest.get("execution_owner") != "project_owner":
        errors.append("source manifest execution_owner must be project_owner")

    profiles = Counter()
    conversion_outputs: dict[Path, tuple[str, str]] = {}
    conversion_output_rows: dict[Path, list[IntentSample]] = {}
    conversion_inputs: dict[Path, tuple[str, str, int]] = {}
    for path, report in conversion_reports:
        if report.get("schema_version") != 1:
            errors.append(f"conversion report schema_version is invalid: {path}")
        profile = report.get("adapter_profile")
        if isinstance(profile, str):
            profiles[profile] += 1
        converted = report.get("converted")
        expected_metadata = EXPECTED_CONVERSION_METADATA.get(str(profile))
        if expected_metadata is None:
            errors.append(f"conversion uses an unknown adapter profile: {path}")
        else:
            if (
                type(converted) is not int
                or converted <= 0
                or report.get("records_read") != converted
            ):
                errors.append(f"conversion row counts are invalid: {path}")
            if report.get("source") != expected_metadata["source"]:
                errors.append(f"conversion source does not match its adapter profile: {path}")
            if report.get("split") != expected_metadata["split"]:
                errors.append(f"conversion split does not match its adapter profile: {path}")
            if report.get("action_provenance") != {
                expected_metadata["action_provenance"]: converted
            }:
                errors.append(
                    f"conversion action provenance does not match its adapter profile: {path}"
                )
            if report.get("risk_labels") != {expected_metadata["risk_label"]: converted}:
                errors.append(f"conversion risk labels do not match its adapter profile: {path}")
        if report.get("status") != "converted_unverified":
            errors.append(f"conversion status is not converted_unverified: {path}")
        if report.get("skipped") != 0:
            errors.append(f"conversion skipped rows are nonzero: {path}")
        for field in ("input", "output"):
            raw_path = report.get(field)
            expected_hash = report.get(f"{field}_sha256")
            if not isinstance(raw_path, str) or not isinstance(expected_hash, str):
                errors.append(f"conversion {field} provenance is incomplete: {path}")
                continue
            artifact = _resolve_project_path(raw_path)
            if not artifact.is_file():
                errors.append(f"conversion {field} artifact is missing: {artifact}")
            elif _sha256(artifact) != expected_hash:
                errors.append(f"conversion {field} hash mismatch: {artifact}")
            if field == "input":
                if artifact in conversion_inputs:
                    errors.append(f"multiple conversion reports claim the same input: {artifact}")
                if isinstance(profile, str) and isinstance(expected_hash, str):
                    conversion_inputs[artifact] = (
                        expected_hash,
                        profile,
                        converted if type(converted) is int else -1,
                    )
        raw_output = report.get("output")
        output_hash = report.get("output_sha256")
        if isinstance(raw_output, str) and isinstance(output_hash, str) and isinstance(profile, str):
            resolved_output = _resolve_project_path(raw_output)
            if resolved_output in conversion_outputs:
                errors.append(f"multiple conversion reports claim the same output: {resolved_output}")
            conversion_outputs[resolved_output] = (output_hash, profile)
            if resolved_output.is_file() and expected_metadata is not None:
                canonical_rows = read_jsonl(resolved_output)
                conversion_output_rows[resolved_output] = canonical_rows
                if len(canonical_rows) != converted:
                    errors.append(f"conversion output row count does not match report: {path}")
                if any(row.adapter_profile != profile for row in canonical_rows):
                    errors.append(f"conversion output adapter profile mismatch: {path}")
                if any(row.source != expected_metadata["source"] for row in canonical_rows):
                    errors.append(f"conversion output source mismatch: {path}")
                if any(row.split != expected_metadata["split"] for row in canonical_rows):
                    errors.append(f"conversion output split mismatch: {path}")
                reported_action_counts = report.get("action_provenance")
                if not isinstance(reported_action_counts, dict):
                    errors.append(
                        f"conversion action provenance counts are invalid: {path}"
                    )
                elif Counter(
                    row.action_provenance for row in canonical_rows
                ) != Counter(reported_action_counts):
                    errors.append(f"conversion output action provenance counts mismatch: {path}")
                reported_risk_counts = report.get("risk_labels")
                if not isinstance(reported_risk_counts, dict):
                    errors.append(f"conversion risk label counts are invalid: {path}")
                elif Counter(row.risk_label for row in canonical_rows) != Counter(
                    reported_risk_counts
                ):
                    errors.append(f"conversion output risk label counts mismatch: {path}")
                if sum(row.human_verified for row in canonical_rows) != report.get(
                    "human_verified"
                ):
                    errors.append(f"conversion output human-verified count mismatch: {path}")
                errors.extend(
                    _validate_conversion_replay(
                        report_path=path,
                        report=report,
                        profile=profile,
                        pipeline_config=pipeline_config,
                        canonical_rows=canonical_rows,
                    )
                )
    if profiles != EXPECTED_CONVERSION_PROFILES:
        errors.append(
            "conversion profile counts do not match the seven required C1 conversions: "
            f"expected={dict(EXPECTED_CONVERSION_PROFILES)}, actual={dict(profiles)}"
        )

    conversion_contract = pipeline_config.get("conversion_inputs")
    expected_contract_profiles = set(EXPECTED_CONVERSION_PROFILES) - {"bipia_generated_v1"}
    if (
        not isinstance(conversion_contract, dict)
        or set(conversion_contract) != expected_contract_profiles
    ):
        errors.append("pipeline conversion input contract is missing or incomplete")
        conversion_contract = {}
    for profile in sorted(expected_contract_profiles):
        contract = conversion_contract.get(profile)
        if not isinstance(contract, dict):
            continue
        source_name = contract.get("source")
        relative_paths = contract.get("paths")
        source_target = source_targets.get(str(source_name))
        if (
            source_target is None
            or not isinstance(relative_paths, list)
            or not all(isinstance(path, str) for path in relative_paths)
        ):
            errors.append(f"conversion input contract is invalid: {profile}")
            continue
        expected_inputs = {(source_target / path).resolve() for path in relative_paths}
        actual_inputs = {
            path for path, (_, input_profile, _) in conversion_inputs.items() if input_profile == profile
        }
        if actual_inputs != expected_inputs:
            errors.append(f"conversion inputs do not match the frozen source paths: {profile}")
        source_inventory = source_artifacts.get(str(source_name), {})
        for path in actual_inputs:
            report_hash = conversion_inputs[path][0]
            inventory = source_inventory.get(path)
            if inventory is None or inventory[1] != report_hash:
                errors.append(
                    f"conversion input is not bound to source-manifest inventory: {profile}/{path}"
                )

    builder_contract = pipeline_config.get("bipia_builder")
    if not isinstance(builder_contract, dict):
        errors.append("pipeline BIPIA builder contract is missing")
        builder_contract = {}
    frozen_bipia = source_registry.get("bipia")
    expected_revision = (
        frozen_bipia.get("revision") if isinstance(frozen_bipia, dict) else None
    )
    if builder_report.get("status") not in {"generated_verified", "reproduced_verified"}:
        errors.append("BIPIA builder report does not contain verified evidence")
    if builder_report.get("execution_owner") != "project_owner":
        errors.append("BIPIA builder report execution_owner must be project_owner")
    if (
        builder_report.get("task") != builder_contract.get("task")
        or builder_report.get("seed") != builder_contract.get("seed")
        or builder_report.get("expected_revision") != expected_revision
        or builder_report.get("actual_revision") != expected_revision
    ):
        errors.append("BIPIA builder task/seed/revision does not match the frozen contract")
    builder_manifest = builder_report.get("source_manifest")
    if (
        not isinstance(builder_manifest, dict)
        or not isinstance(builder_manifest.get("path"), str)
        or _resolve_project_path(builder_manifest["path"]) != source_manifest_path.resolve()
        or builder_manifest.get("file_sha256") != _sha256(source_manifest_path)
    ):
        errors.append("BIPIA builder report is not bound to the current source manifest")
    bipia_inventory = source_artifacts.get("bipia", {})
    bipia_target = source_targets.get("bipia")
    for field in ("contexts", "attacks"):
        evidence = builder_report.get(field)
        expected_raw = builder_contract.get(field)
        expected_path = (
            (bipia_target / expected_raw).resolve()
            if bipia_target is not None and isinstance(expected_raw, str)
            else None
        )
        inventory_evidence = bipia_inventory.get(expected_path) if expected_path else None
        if (
            not isinstance(evidence, dict)
            or not isinstance(evidence.get("path"), str)
            or _resolve_project_path(evidence["path"]) != expected_path
            or inventory_evidence is None
            or evidence.get("size") != inventory_evidence[0]
            or evidence.get("sha256") != inventory_evidence[1]
        ):
            errors.append(f"BIPIA builder {field} is not bound to the source inventory")
    builder_output = builder_report.get("output")
    if builder_report.get("status") == "reproduced_verified":
        reproduction = builder_report.get("reproduction")
        if (
            not isinstance(reproduction, dict)
            or not isinstance(builder_output, dict)
            or reproduction.get("rows") != builder_output.get("rows")
            or reproduction.get("sha256") != builder_output.get("sha256")
        ):
            errors.append("BIPIA builder reproduction evidence is missing or inconsistent")
    environment = builder_report.get("environment")
    required_builder_packages = {
        "PyYAML",
        "jsonlines",
        "nltk",
        "numpy",
        "pandas",
        "transformers",
    }
    packages = environment.get("packages") if isinstance(environment, dict) else None
    if (
        not isinstance(environment, dict)
        or not isinstance(environment.get("python"), str)
        or not environment["python"]
        or not isinstance(packages, dict)
        or set(packages) != required_builder_packages
        or any(not isinstance(version, str) or version in {"", "not-installed"} for version in packages.values())
    ):
        errors.append("BIPIA builder environment evidence is missing")
    generated_inputs = [
        (path, evidence)
        for path, evidence in conversion_inputs.items()
        if evidence[1] == "bipia_generated_v1"
    ]
    if len(generated_inputs) != 1:
        errors.append("BIPIA generated conversion input is missing or ambiguous")
    else:
        generated_input, (generated_hash, _, generated_rows) = generated_inputs[0]
        if (
            not isinstance(builder_output, dict)
            or not isinstance(builder_output.get("path"), str)
            or _resolve_project_path(builder_output["path"]) != generated_input
            or builder_output.get("sha256") != generated_hash
            or builder_output.get("rows") != generated_rows
        ):
            errors.append("BIPIA builder output is not bound to the generated conversion input")

    if merge_report.get("status") != "merged_unverified":
        errors.append("merge report status is not merged_unverified")
    merge_inputs = merge_report.get("inputs")
    if not isinstance(merge_inputs, list):
        errors.append("merge report inputs are missing or invalid")
        merge_inputs = []
    expected_merge_inputs = {
        path
        for path, (_, profile) in conversion_outputs.items()
        if profile in {"bipia_generated_v1", "bipia_clean_v1"}
    }
    actual_merge_inputs: set[Path] = set()
    for entry in merge_inputs:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            errors.append("merge report contains an invalid input entry")
            continue
        path = _resolve_project_path(entry["path"])
        if path in actual_merge_inputs:
            errors.append(f"merge report contains a duplicate input entry: {path}")
        actual_merge_inputs.add(path)
        conversion = conversion_outputs.get(path)
        canonical_rows = conversion_output_rows.get(path)
        if (
            conversion is None
            or entry.get("sha256") != conversion[0]
            or canonical_rows is None
            or entry.get("rows") != len(canonical_rows)
        ):
            errors.append(f"merge input is not bound to a required conversion output: {path}")
    if actual_merge_inputs != expected_merge_inputs:
        errors.append("merge inputs do not exactly match BIPIA clean/generated conversion outputs")
    raw_merge_output = merge_report.get("output")
    merge_output_hash = merge_report.get("output_sha256")
    merge_output = (
        _resolve_project_path(raw_merge_output) if isinstance(raw_merge_output, str) else None
    )
    if (
        merge_output is None
        or not merge_output.is_file()
        or not isinstance(merge_output_hash, str)
        or _sha256(merge_output) != merge_output_hash
    ):
        errors.append("merge output path/hash is invalid")
    merge_rows: list[IntentSample] | None = None
    if merge_output is not None and merge_output.is_file():
        merge_rows = read_jsonl(merge_output)
    expected_merge_rows = [
        row
        for path in sorted(expected_merge_inputs)
        for row in conversion_output_rows.get(path, [])
    ]
    if set(conversion_output_rows) >= expected_merge_inputs:
        if merge_rows is None or Counter(
            _sample_signature(row) for row in merge_rows
        ) != Counter(_sample_signature(row) for row in expected_merge_rows):
            errors.append(
                "merge output sample multiset does not exactly equal its BIPIA conversion outputs"
            )
    else:
        errors.append("BIPIA conversion outputs are unavailable for merge replay")
    if merge_rows is not None:
        duplicate_ids = sorted(
            sample_id
            for sample_id, count in Counter(row.sample_id for row in merge_rows).items()
            if count > 1
        )
        if duplicate_ids:
            errors.append(
                "merge output contains duplicate sample IDs: " + ", ".join(duplicate_ids[:10])
            )
        if merge_report.get("rows") != len(merge_rows):
            errors.append("merge report row count does not match its actual output")
        if len(merge_rows) != len(expected_merge_rows):
            errors.append("merge output row count does not match its conversion outputs")
        if merge_report.get("sources") != dict(
            sorted(Counter(row.source for row in merge_rows).items())
        ):
            errors.append("merge report source counts do not match its actual output")
        if merge_report.get("risk_labels") != dict(
            sorted(Counter(row.risk_label for row in merge_rows).items())
        ):
            errors.append("merge report risk-label counts do not match its actual output")
        if merge_report.get("human_verified") != sum(
            row.human_verified for row in merge_rows
        ):
            errors.append("merge report human-verified count does not match its actual output")

    audit_key_hash = _sha256(audit_key_path) if audit_key_path.is_file() else None
    if merge_output is not None:
        if (
            not isinstance(audit_key.get("input"), str)
            or _resolve_project_path(audit_key["input"]) != merge_output
            or audit_key.get("input_sha256") != merge_output_hash
        ):
            errors.append("audit key is not bound to the merge output")
        if (
            not isinstance(audit_summary.get("audited_input"), str)
            or _resolve_project_path(audit_summary["audited_input"]) != merge_output
            or audit_summary.get("audited_input_sha256") != merge_output_hash
            or not isinstance(audit_application.get("input"), str)
            or _resolve_project_path(audit_application["input"]) != merge_output
            or audit_application.get("input_sha256") != merge_output_hash
        ):
            errors.append("audit summary/application is not bound to the merge output")
    raw_audit_sheet = audit_summary.get("audit_sheet")
    audit_sheet = (
        _resolve_project_path(raw_audit_sheet) if isinstance(raw_audit_sheet, str) else None
    )
    if (
        audit_key_hash is None
        or audit_summary.get("audit_key_sha256") != audit_key_hash
        or audit_application.get("audit_key_sha256") != audit_key_hash
        or audit_summary.get("audit_sheet_sha256") != audit_application.get("audit_sha256")
        or audit_sheet is None
        or not audit_sheet.is_file()
        or _sha256(audit_sheet) != audit_summary.get("audit_sheet_sha256")
        or not isinstance(audit_key.get("audit_sheet"), str)
        or _resolve_project_path(audit_key["audit_sheet"]) != audit_sheet
        or not isinstance(audit_application.get("audit"), str)
        or _resolve_project_path(audit_application["audit"]) != audit_sheet
        or not isinstance(audit_summary.get("audit_key"), str)
        or _resolve_project_path(audit_summary["audit_key"]) != audit_key_path.resolve()
        or not isinstance(audit_application.get("audit_key"), str)
        or _resolve_project_path(audit_application["audit_key"]) != audit_key_path.resolve()
    ):
        errors.append("audit summary and application do not use the same sheet/key hashes")
    raw_audited_output = audit_application.get("output")
    audited_output_hash = audit_application.get("output_sha256")
    audited_output = (
        _resolve_project_path(raw_audited_output) if isinstance(raw_audited_output, str) else None
    )
    if (
        audited_output is None
        or not audited_output.is_file()
        or not isinstance(audited_output_hash, str)
        or _sha256(audited_output) != audited_output_hash
    ):
        errors.append("audited output path/hash is invalid")

    primary_input = split_manifest.get("primary_input")
    if not isinstance(primary_input, dict):
        errors.append("split manifest primary_input evidence is missing")
    elif (
        audited_output is None
        or not isinstance(primary_input.get("path"), str)
        or _resolve_project_path(primary_input["path"]) != audited_output
        or primary_input.get("sha256") != audited_output_hash
    ):
        errors.append("split manifest primary input is not bound to the audited output")
    fixed_inputs = split_manifest.get("fixed_inputs")
    actual_fixed_inputs: dict[Path, str] = {}
    if not isinstance(fixed_inputs, dict):
        errors.append("split manifest fixed input evidence is missing")
    else:
        for split, entries in fixed_inputs.items():
            if split not in {"test_b", "test_c"} or not isinstance(entries, list):
                errors.append(f"split manifest fixed input entry is invalid: {split}")
                continue
            for entry in entries:
                if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                    errors.append(f"split manifest fixed input item is invalid: {split}")
                    continue
                path = _resolve_project_path(entry["path"])
                actual_fixed_inputs[path] = str(entry.get("sha256", ""))
                conversion = conversion_outputs.get(path)
                canonical_rows = conversion_output_rows.get(path)
                if (
                    conversion is None
                    or entry.get("sha256") != conversion[0]
                    or canonical_rows is None
                    or entry.get("rows") != len(canonical_rows)
                ):
                    errors.append(
                        f"fixed split input is not bound to a required conversion output: {path}"
                    )
    expected_fixed_inputs = {
        path: output_hash
        for path, (output_hash, profile) in conversion_outputs.items()
        if profile not in {"bipia_generated_v1", "bipia_clean_v1"}
    }
    if actual_fixed_inputs != expected_fixed_inputs:
        errors.append("fixed split inputs do not exactly match the five external conversions")

    split_contract = pipeline_config.get("split")
    if not isinstance(split_contract, dict):
        errors.append("pipeline split contract is missing")
        split_contract = {}
    if split_manifest.get("seed") != split_contract.get("seed"):
        errors.append("split manifest seed does not match the pipeline contract")
    if split_manifest.get("ratios") != split_contract.get("ratios"):
        errors.append("split manifest ratios do not match the pipeline contract")
    deduplication = split_manifest.get("deduplication")
    if (
        not isinstance(deduplication, dict)
        or deduplication.get("near_threshold")
        != split_contract.get("near_duplicate_threshold")
    ):
        errors.append("split manifest near-duplicate threshold does not match the contract")

    for name, report in (
        ("audit summary", audit_summary),
        ("audit application", audit_application),
        ("context integrity", context_integrity),
        ("external action integrity", external_action_integrity),
    ):
        if report.get("status") != "passed":
            errors.append(f"{name} status is not passed")
        if report.get("errors") != []:
            errors.append(f"{name} contains validation errors")
    context_manifest = context_integrity.get("manifest")
    manifest_file_hash = _sha256(split_manifest_path)
    context_manifest_valid = isinstance(context_manifest, dict)
    if (
        context_integrity.get("input_mode") != "context"
        or context_integrity.get("near_duplicate_check_performed") is not True
        or context_integrity.get("near_threshold")
        != split_contract.get("near_duplicate_threshold")
        or not context_manifest_valid
        or not isinstance(context_manifest.get("path"), str)
        or _resolve_project_path(context_manifest["path"]) != split_manifest_path.resolve()
        or context_manifest.get("file_sha256") != manifest_file_hash
        or context_manifest.get("sealed_sha256") != split_manifest.get("sha256")
    ):
        errors.append("context integrity report is not bound to the sealed manifest/full check")
    manifest_files = split_manifest.get("files", {})
    expected_split_evidence = {
        split: (split_manifest_path.resolve().parent / entry["path"]).resolve()
        for split, entry in manifest_files.items()
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    }
    for report_name, report, expected_roles in (
        ("context integrity", context_integrity, set(C1_REQUIRED_SPLITS)),
        ("external action integrity", external_action_integrity, {"test_b", "test_c"}),
    ):
        inputs = report.get("inputs")
        if not isinstance(inputs, dict) or set(inputs) != expected_roles:
            errors.append(f"{report_name} inputs do not contain the required roles")
            continue
        for split, entry in inputs.items():
            manifest_entry = manifest_files.get(split)
            if (
                not isinstance(entry, dict)
                or not isinstance(entry.get("path"), str)
                or not isinstance(manifest_entry, dict)
                or _resolve_project_path(entry["path"]) != expected_split_evidence.get(split)
                or entry.get("sha256") != manifest_entry.get("sha256")
                or entry.get("rows") != manifest_entry.get("rows")
            ):
                errors.append(f"{report_name} input is not bound to manifest role: {split}")
    if external_action_integrity.get("input_mode") != "action":
        errors.append("external action integrity report was not produced in action mode")
    action_manifest = external_action_integrity.get("manifest")
    if (
        not isinstance(action_manifest, dict)
        or not isinstance(action_manifest.get("path"), str)
        or _resolve_project_path(action_manifest["path"]) != split_manifest_path.resolve()
        or action_manifest.get("file_sha256") != manifest_file_hash
        or action_manifest.get("sealed_sha256") != split_manifest.get("sha256")
    ):
        errors.append("external action integrity report is not bound to the sealed manifest")
    expected_config_hash = _sha256(DEFAULT_CONFIG)
    for report_name, report in (
        ("context integrity", context_integrity),
        ("external action integrity", external_action_integrity),
    ):
        report_config = report.get("config")
        if (
            not isinstance(report_config, dict)
            or not isinstance(report_config.get("path"), str)
            or _resolve_project_path(report_config["path"]) != DEFAULT_CONFIG.resolve()
            or report_config.get("file_sha256") != expected_config_hash
        ):
            errors.append(f"{report_name} is not bound to the canonical pipeline config")
    audit_contract = pipeline_config.get("audit")
    configured_minimum = (
        audit_contract.get("minimum_rows") if isinstance(audit_contract, dict) else None
    )
    if type(configured_minimum) is not int or configured_minimum <= 0:
        errors.append("pipeline audit minimum_rows is missing or invalid")
        configured_minimum = minimum_audit_rows
    if minimum_audit_rows < configured_minimum:
        errors.append("requested audit minimum cannot be lower than the pipeline contract")
    effective_minimum = max(minimum_audit_rows, configured_minimum)
    selected_rows = audit_key.get("selected")
    completed_summary_rows = audit_summary.get("completed_rows")
    completed_application_rows = audit_application.get("completed_rows")
    if type(selected_rows) is not int or selected_rows < effective_minimum:
        errors.append("audit key does not select the required number of rows")
    if type(completed_summary_rows) is not int or completed_summary_rows < effective_minimum:
        errors.append(
            f"completed audit rows {completed_summary_rows} "
            f"< required {effective_minimum}"
        )
    if (
        type(completed_application_rows) is not int
        or completed_application_rows < effective_minimum
    ):
        errors.append("audit application does not cover the required completed audit rows")
    errors.extend(
        _validate_audit_replay(
            pipeline_config=pipeline_config,
            audit_key=audit_key,
            audit_key_path=audit_key_path,
            audit_summary=audit_summary,
            audit_application=audit_application,
            audit_sheet=audit_sheet,
            merge_output=merge_output,
            merge_rows=merge_rows,
            audited_output=audited_output,
            effective_minimum=effective_minimum,
        )
    )
    return errors


def _render_label_report(
    statistics: dict[str, Any],
    audit_summary: dict[str, Any],
    audit_application: dict[str, Any],
) -> str:
    risk_alignment = statistics["risk_alignment"]
    lines = [
        "# C1 label quality report",
        "",
        "Status: generated from project-owner data artifacts; review the machine-readable statistics alongside this report.",
        "",
        "## Human audit",
        "",
        f"- Completed rows: {audit_summary.get('completed_rows', 0)}",
        f"- Decisions: `{json.dumps(audit_summary.get('status_counts', {}), sort_keys=True)}`",
        f"- Decision rates: `{json.dumps(audit_summary.get('status_rates', {}), sort_keys=True)}`",
        f"- Reviewer counts: `{json.dumps(audit_summary.get('reviewer_counts', {}), sort_keys=True)}`",
        f"- Applied outcomes: `{json.dumps(audit_application.get('application_counts', {}), sort_keys=True)}`",
        "- Inter-reviewer agreement: not measured unless a separately versioned second-review artifact is supplied.",
        "",
        "## Risk × Alignment contingency",
        "",
        "Scope: train split only; final-test labels are not used for this dependency decision.",
        "",
        "| Risk label | Alignment 0 | Alignment 1 |",
        "|---|---:|---:|",
    ]
    for label in RISK_LABELS:
        row = risk_alignment["contingency"][label]
        lines.append(f"| {label} | {row['0']} | {row['1']} |")
    lines.extend(
        [
            "",
            f"- Mutual information: {risk_alignment['mutual_information_bits']:.8f} bits "
            f"({risk_alignment['mutual_information_nats']:.8f} nats).",
            f"- Alignment entropy: {risk_alignment['alignment_entropy_bits']:.8f} bits.",
            "- Alignment is deterministic from risk: "
            f"`{str(risk_alignment['alignment_is_deterministic_from_risk']).lower()}`.",
            "",
            "The full conditional-probability tables are stored in `dataset_statistics.json`. "
            "A deterministic mapping means the auxiliary label contains no independent label "
            "information; only a preregistered model ablation can test optimization effects.",
            "",
        ]
    )
    return "\n".join(lines)


def _render_data_card(
    statistics: dict[str, Any],
    source_manifest: dict[str, Any],
    split_manifest: dict[str, Any],
    conversion_reports: list[tuple[Path, dict[str, Any]]],
) -> str:
    readiness = statistics["training_readiness"]
    lines = [
        "# IntentFence C1 data card",
        "",
        "Status: project-owner generated derivative dataset. The BIPIA training pool has a human-label audit gate; Test B/C have schema, provenance, and integrity gates but not an equivalent human-label audit.",
        "",
        "## Version and intended use",
        "",
        f"- Split manifest SHA-256: `{split_manifest.get('sha256', 'missing')}`",
        "- Intended use: offline research on indirect prompt-injection detection under the frozen IntentFence protocol.",
        "- Not intended for: production safety guarantees, authorization decisions, or claims about observed Agent actions.",
        "",
        "## Sources",
        "",
        "| Source | Revision | License finding |",
        "|---|---|---|",
    ]
    for row in sorted(source_manifest.get("sources", []), key=lambda item: item["name"]):
        lines.append(
            f"| {row['name']} | `{row['revision']}` | {row.get('license_finding', 'unrecorded')} |"
        )
    lines.extend(
        [
            "",
            "## Split composition",
            "",
            "| Split | Rows | Risk counts | Action provenance |",
            "|---|---:|---|---|",
        ]
    )
    for split in C1_REQUIRED_SPLITS:
        summary = statistics["by_split"][split]
        lines.append(
            f"| {split} | {summary['total']} | "
            f"`{json.dumps(summary['risk_labels'], sort_keys=True)}` | "
            f"`{json.dumps(summary['action_provenance'], sort_keys=True)}` |"
        )
    lines.extend(
        [
            "",
            "## Conversion provenance",
            "",
            "| Adapter profile | Converted | Skipped | Output SHA-256 |",
            "|---|---:|---:|---|",
        ]
    )
    for _, report in conversion_reports:
        lines.append(
            f"| {report.get('adapter_profile', 'unknown')} | "
            f"{report.get('converted', 'unknown')} | {report.get('skipped', 'unknown')} | "
            f"`{report.get('output_sha256', 'missing')}` |"
        )
    lines.extend(
        [
            "",
            "## Training-readiness findings",
            "",
            "- Assessment scope: class presence and action-evidence gates only; this is not formal training authorization.",
            "- Binary benign/attack class coverage present in train: "
            f"`{str(readiness['binary_attack_train_class_coverage_present']).lower()}`",
            "- Five-class coverage present in train: "
            f"`{str(readiness['five_class_train_class_coverage_present']).lower()}`",
            f"- Missing train risk labels: `{json.dumps(readiness['missing_train_risk_labels'])}`",
            "- Minimum per-class support assessed: `false`.",
            "- Alignment target has independent label information: "
            f"`{str(readiness['alignment_auxiliary_target_has_independent_label_information']).lower()}`",
            f"- Model C action data ready: `{str(readiness['model_c_action_data_ready']).lower()}`",
            "- Formal training authorized: `false` (project-owner protocol/action-route decision pending).",
            "",
            "## Action-evidence boundaries",
            "",
            "- BIPIA rows do not provide a real proposed action until a separately approved and audited action-construction stage exists.",
            "- InjecAgent `benchmark_target` is a benchmark target, not an observed Agent proposal or tool call.",
            "- NotInject `protocol_wrapper` is a fixed over-defense probe, not source-provided Agent behavior.",
            "",
            "## Known limitations",
            "",
            "- External detector training overlap is not known at membership level.",
            "- NotInject is a small trigger-enriched stress set, not representative benign traffic.",
            "- A missing risk class in train cannot support a five-class learned claim for that class.",
            "- Human-verified flags apply only to reviewed rows; unreviewed retained rows remain unverified.",
            "- Test B/C labels pass schema and integrity checks but are not covered by the BIPIA human-audit sample.",
            "- Final-test label counts are descriptive provenance already sealed in the manifest and must not be used to tune models, thresholds, or configurations.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_outputs_atomically(payloads: dict[Path, str]) -> None:
    parents = {path.parent.resolve() for path in payloads}
    if len(parents) != 1:
        raise ValueError("C1 report outputs must share one directory for atomic publication")
    output_parent = parents.pop()
    output_parent.mkdir(parents=True, exist_ok=True)
    committed: list[Path] = []
    with tempfile.TemporaryDirectory(prefix=".c1-reports-", dir=output_parent) as raw_temp:
        temporary = Path(raw_temp)
        staged: list[tuple[Path, Path]] = []
        for index, (destination, content) in enumerate(payloads.items()):
            stage = temporary / f"{index}.tmp"
            stage.write_text(content, encoding="utf-8")
            staged.append((stage, destination))
        try:
            for stage, destination in staged:
                stage.replace(destination)
                committed.append(destination)
        except OSError:
            for destination in committed:
                destination.unlink(missing_ok=True)
            raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build C1 statistics, label-quality report, and data card from owner artifacts"
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--input", action="append", type=_input_spec, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--builder-report", type=Path, required=True)
    parser.add_argument("--conversion-report", action="append", type=Path, required=True)
    parser.add_argument("--merge-report", type=Path, required=True)
    parser.add_argument("--audit-key", type=Path, required=True)
    parser.add_argument("--audit-summary", type=Path, required=True)
    parser.add_argument("--audit-application", type=Path, required=True)
    parser.add_argument("--context-integrity", type=Path, required=True)
    parser.add_argument("--external-action-integrity", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("configs/data_pipeline.yaml"))
    parser.add_argument("--minimum-audit-rows", type=int, default=200)
    parser.add_argument("--statistics-output", type=Path, required=True)
    parser.add_argument("--label-report-output", type=Path, required=True)
    parser.add_argument("--data-card-output", type=Path, required=True)
    args = parser.parse_args()

    outputs = tuple(
        _resolve_project_path(path)
        for path in (args.statistics_output, args.label_report_output, args.data_card_output)
    )
    if len(set(outputs)) != len(outputs):
        raise ValueError("C1 report output paths must be distinct")
    existing = [path for path in outputs if path.exists()]
    if existing:
        raise FileExistsError(
            "Refusing to overwrite C1 report outputs: " + ", ".join(map(str, existing))
        )
    input_paths: dict[str, Path] = {}
    for split, path in args.input:
        if split in input_paths:
            raise ValueError(f"Duplicate --input role: {split}")
        input_paths[split] = _resolve_project_path(path)
    if set(input_paths) != set(C1_REQUIRED_SPLITS):
        raise ValueError("C1 reports require exactly the six sealed split roles")

    manifest_path = _resolve_project_path(args.manifest)
    manifest_errors = audit_split_manifest(
        manifest_path,
        expected_splits=C1_REQUIRED_SPLITS,
        supplied_paths=input_paths,
    )
    if manifest_errors:
        raise ValueError("Split manifest failed validation: " + "; ".join(manifest_errors))

    pipeline_config, source_registry = _load_pipeline_contract(args.config)
    audit_contract = pipeline_config.get("audit")
    configured_minimum = (
        audit_contract.get("minimum_rows") if isinstance(audit_contract, dict) else None
    )
    if type(configured_minimum) is not int or configured_minimum <= 0:
        raise ValueError("Canonical pipeline config has an invalid audit minimum")
    if args.minimum_audit_rows < configured_minimum:
        raise ValueError(
            f"--minimum-audit-rows cannot be lower than the frozen minimum {configured_minimum}"
        )
    conversion_paths = [_resolve_project_path(path) for path in args.conversion_report]
    if len(conversion_paths) != sum(EXPECTED_CONVERSION_PROFILES.values()):
        raise ValueError("C1 reports require exactly seven conversion reports")
    if len(set(conversion_paths)) != len(conversion_paths):
        raise ValueError("C1 conversion report paths must be unique")
    source_manifest_path = _resolve_project_path(args.source_manifest)
    builder_report_path = _resolve_project_path(args.builder_report)
    merge_report_path = _resolve_project_path(args.merge_report)
    audit_key_path = _resolve_project_path(args.audit_key)
    audit_summary_path = _resolve_project_path(args.audit_summary)
    audit_application_path = _resolve_project_path(args.audit_application)
    context_integrity_path = _resolve_project_path(args.context_integrity)
    external_action_integrity_path = _resolve_project_path(args.external_action_integrity)
    source_manifest = _load_json(source_manifest_path)
    builder_report = _load_json(builder_report_path)
    conversion_reports = [(path, _load_json(path)) for path in conversion_paths]
    merge_report = _load_json(merge_report_path)
    audit_key = _load_json(audit_key_path)
    audit_summary = _load_json(audit_summary_path)
    audit_application = _load_json(audit_application_path)
    context_integrity = _load_json(context_integrity_path)
    external_action_integrity = _load_json(external_action_integrity_path)
    split_manifest = _load_json(manifest_path)
    errors = _validate_evidence(
        source_manifest=source_manifest,
        source_manifest_path=source_manifest_path,
        source_registry=source_registry,
        pipeline_config=pipeline_config,
        builder_report=builder_report,
        conversion_reports=conversion_reports,
        merge_report=merge_report,
        audit_key=audit_key,
        audit_key_path=audit_key_path,
        audit_summary=audit_summary,
        audit_application=audit_application,
        split_manifest=split_manifest,
        split_manifest_path=manifest_path,
        context_integrity=context_integrity,
        external_action_integrity=external_action_integrity,
        minimum_audit_rows=args.minimum_audit_rows,
    )
    if errors:
        raise ValueError("C1 evidence is incomplete: " + "; ".join(errors))

    action_policy = pipeline_config.get("action_evidence_policy")
    if not isinstance(action_policy, dict):
        raise ValueError(f"Action evidence policy is missing or invalid: {args.config}")

    samples_by_split: dict[str, list[IntentSample]] = {}
    for split in C1_REQUIRED_SPLITS:
        rows = read_jsonl(input_paths[split])
        if not rows or any(row.split != split for row in rows):
            raise ValueError(f"Split is empty or contains a mismatched declared role: {split}")
        samples_by_split[split] = rows
    lineage_errors = _validate_split_lineage(
        samples_by_split=samples_by_split,
        conversion_reports=conversion_reports,
        audit_application=audit_application,
        pipeline_config=pipeline_config,
        split_manifest=split_manifest,
    )
    if lineage_errors:
        raise ValueError("C1 split lineage is invalid: " + "; ".join(lineage_errors))
    statistics = compute_label_statistics(samples_by_split, action_policy)
    statistics["split_manifest_sha256"] = split_manifest.get("sha256")
    statistics["evidence"] = {
        "pipeline_config": {
            "path": str(DEFAULT_CONFIG.relative_to(ROOT)),
            "sha256": _sha256(DEFAULT_CONFIG),
        },
        "source_manifest": {
            "path": str(source_manifest_path),
            "sha256": _sha256(source_manifest_path),
        },
        "bipia_builder_report": {
            "path": str(builder_report_path),
            "sha256": _sha256(builder_report_path),
            "status": builder_report.get("status"),
        },
        "split_manifest": {
            "path": str(manifest_path),
            "file_sha256": _sha256(manifest_path),
            "sealed_sha256": split_manifest.get("sha256"),
        },
    }
    statistics["evidence_status"] = "validated"

    _write_outputs_atomically(
        {
            outputs[0]: json.dumps(
                statistics, indent=2, ensure_ascii=False, sort_keys=True
            )
            + "\n",
            outputs[1]: _render_label_report(statistics, audit_summary, audit_application),
            outputs[2]: _render_data_card(
                statistics, source_manifest, split_manifest, conversion_reports
            ),
        }
    )
    print(
        json.dumps(
            {
                "evidence_status": "validated",
                "total_rows": statistics["total_rows"],
                "training_readiness": statistics["training_readiness"],
                "outputs": [str(path) for path in outputs],
            },
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
