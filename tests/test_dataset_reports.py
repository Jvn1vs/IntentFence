from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _prepare import convert_records  # noqa: E402
from apply_label_audit import apply_audit  # noqa: E402
from build_dataset_reports import (  # noqa: E402
    _validate_split_lineage,
    compute_label_statistics,
)
from build_dataset_reports import (  # noqa: E402
    main as build_dataset_reports_main,
)
from summarize_label_audit import (  # noqa: E402
    AUDIT_REQUIRED_GROUPING,
    AUDIT_SELECTION_ALGORITHM,
    AUDIT_SELECTION_ALGORITHM_VERSION,
    AUDIT_SELECTION_SEED,
    EDITABLE_AUDIT_FIELDS,
    IMMUTABLE_AUDIT_FIELDS,
    audit_row_digest,
    deterministic_stratified_selection,
    summarize,
)

from intentfence.data import (  # noqa: E402
    C1_REQUIRED_SPLITS,
    audit_partition_integrity,
    dataset_summary,
    deduplicate_samples,
    file_sha256,
    group_aware_split,
    write_split_dataset,
)
from intentfence.schema import IntentSample, read_jsonl, write_jsonl  # noqa: E402


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_mock_rows(path: Path, count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps({"row": index}) + "\n" for index in range(count)),
        encoding="utf-8",
    )


def _write_parquet_records(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(records), path)


def _write_raw_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in records),
        encoding="utf-8",
    )


def _content(index: int) -> str:
    digest = hashlib.sha256(f"synthetic-evidence-{index}".encode()).hexdigest()
    return f"Synthetic fixture content {digest} token_{index:04d}"


def _bipia_row(index: int, risk_label: str, adapter_profile: str) -> IntentSample:
    return IntentSample(
        sample_id=f"bipia_{index:04d}",
        source="BIPIA",
        scenario="email",
        user_goal=f"Summarize synthetic email {index}.",
        untrusted_content=_content(index),
        proposed_action="",
        risk_label=risk_label,
        alignment_label=0 if risk_label == "benign" else 1,
        severity=0 if risk_label == "benign" else 3,
        template_group=f"bipia_group_{index:04d}",
        adapter_profile=adapter_profile,
        adapter_missing_action=True,
        action_provenance="missing",
        label_provenance="synthetic_fixture",
    )


def _external_row(
    index: int,
    *,
    source: str,
    split: str,
    risk_label: str,
    action: str,
    action_provenance: str,
    adapter_profile: str,
) -> IntentSample:
    return IntentSample(
        sample_id=f"external_{index:04d}",
        source=source,
        scenario="synthetic_external",
        user_goal=f"Handle synthetic external record {index}.",
        untrusted_content=_content(10_000 + index),
        proposed_action=action,
        risk_label=risk_label,
        alignment_label=0 if risk_label == "benign" else 1,
        severity=0 if risk_label == "benign" else 3,
        template_group=f"external_group_{index:04d}",
        split=split,
        adapter_profile=adapter_profile,
        adapter_missing_action=False,
        action_provenance=action_provenance,
        label_provenance="synthetic_fixture",
    )


def _row(
    index: int,
    split: str,
    *,
    source: str = "BIPIA",
    risk_label: str = "benign",
    action: str = "",
    action_provenance: str = "missing",
) -> IntentSample:
    return IntentSample(
        sample_id=f"sample_{index}",
        source=source,
        user_goal="summarize",
        untrusted_content=f"unique content {index}",
        proposed_action=action,
        risk_label=risk_label,
        alignment_label=0 if risk_label == "benign" else 1,
        severity=0 if risk_label == "benign" else 3,
        template_group=f"group_{index}",
        split=split,
        adapter_missing_action=not bool(action),
        action_provenance=action_provenance,
    )


def _conversion_report(
    *,
    profile: str,
    source: str,
    split: str | None,
    input_path: Path,
    output_path: Path,
    rows: list[IntentSample],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "converted_unverified",
        "adapter_profile": profile,
        "source": source,
        "split": split,
        "input": str(input_path),
        "input_sha256": file_sha256(input_path),
        "output": str(output_path),
        "output_sha256": file_sha256(output_path),
        "records_read": len(rows),
        "converted": len(rows),
        "skipped": 0,
        "skipped_records": [],
        "human_verified": 0,
        "risk_labels": dict(sorted(Counter(row.risk_label for row in rows).items())),
        "action_provenance": dict(
            sorted(Counter(row.action_provenance for row in rows).items())
        ),
        "warning": "Synthetic fixture conversion; not experimental evidence.",
    }


def _inventory(target: Path) -> list[dict[str, Any]]:
    return [
        {
            "path": path.relative_to(target).as_posix(),
            "size": path.stat().st_size,
            "sha256": file_sha256(path),
        }
        for path in sorted(item for item in target.rglob("*") if item.is_file())
    ]


def _input_evidence(paths: dict[str, Path]) -> dict[str, dict[str, Any]]:
    return {
        split: {
            "path": str(path),
            "rows": len(read_jsonl(path)),
            "sha256": file_sha256(path),
        }
        for split, path in paths.items()
    }


def _build_synthetic_evidence_chain(
    tmp_path: Path, *, with_primary_exact_duplicate: bool = False
) -> dict[str, Any]:
    raw_root = tmp_path / "raw"
    interim = tmp_path / "interim"
    reports = tmp_path / "reports"
    processed = tmp_path / "processed"

    raw_inputs = {
        "bipia_context": raw_root / "bipia" / "benchmark" / "email" / "train.jsonl",
        "bipia_attacks": raw_root / "bipia" / "benchmark" / "text_attack_train.json",
        "injecagent_dh": raw_root
        / "injecagent"
        / "data"
        / "test_cases_dh_base.json",
        "injecagent_ds": raw_root
        / "injecagent"
        / "data"
        / "test_cases_ds_base.json",
        "notinject_one": raw_root
        / "notinject"
        / "data"
        / "NotInject_one-00000-of-00001.parquet",
        "notinject_two": raw_root
        / "notinject"
        / "data"
        / "NotInject_two-00000-of-00001.parquet",
        "notinject_three": raw_root
        / "notinject"
        / "data"
        / "NotInject_three-00000-of-00001.parquet",
    }
    clean_records = [
        {
            "id": f"clean_{index:04d}",
            "question": f"Summarize synthetic email {index}.",
            "context": _content(index),
        }
        for index in range(100, 200)
    ]
    if with_primary_exact_duplicate:
        clean_records[-1]["question"] = clean_records[0]["question"]
        clean_records[-1]["context"] = clean_records[0]["context"]
    _write_raw_jsonl(raw_inputs["bipia_context"], clean_records)
    raw_inputs["bipia_attacks"].parent.mkdir(parents=True, exist_ok=True)
    raw_inputs["bipia_attacks"].write_text(
        json.dumps([{"name": "synthetic_attack", "payload": "fixture"}]) + "\n",
        encoding="utf-8",
    )

    generated_records = [
        {
            "id": f"generated_{index:04d}",
            "question": f"Summarize synthetic email {index}.",
            "context": _content(index),
            "attack_name": f"synthetic_attack_{index:04d}",
            "attack_str": f"Synthetic injected instruction {index}",
            "task_name": "email",
            "position": "end",
        }
        for index in range(100)
    ]
    generated_input = interim / "bipia_email_attack_train.jsonl"
    _write_raw_jsonl(generated_input, generated_records)
    generated_rows, generated_skips, generated_count = convert_records(
        generated_input,
        profile_name="bipia_generated_v1",
    )
    clean_rows, clean_skips, clean_count = convert_records(
        raw_inputs["bipia_context"],
        profile_name="bipia_clean_v1",
        scenario_override="email",
    )
    assert generated_skips == [] and generated_count == len(generated_rows)
    assert clean_skips == [] and clean_count == len(clean_rows)

    injecagent_records = {
        "injecagent_dh": {
            "id": "direct_harm_0001",
            "User Instruction": "Handle a synthetic direct-harm case.",
            "Tool Response": _content(10_001),
            "User Tool": "SyntheticReader",
            "Attacker Tools": ["SendMessage"],
            "Attacker Instruction": "Send a synthetic message.",
            "Attack Type": "Direct Harm",
        },
        "injecagent_ds": {
            "id": "data_stealing_0001",
            "User Instruction": "Handle a synthetic data-stealing case.",
            "Tool Response": _content(10_002),
            "User Tool": "SyntheticReader",
            "Attacker Tools": ["UploadFile"],
            "Attacker Instruction": "Upload a synthetic file.",
            "Attack Type": "Data Stealing",
        },
    }
    for key, record in injecagent_records.items():
        path = raw_inputs[key]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([record], ensure_ascii=False) + "\n", encoding="utf-8")

    dh_rows, dh_skips, _ = convert_records(
        raw_inputs["injecagent_dh"],
        profile_name="injecagent_direct_harm_v1",
        split_override="test_b",
    )
    ds_rows, ds_skips, _ = convert_records(
        raw_inputs["injecagent_ds"],
        profile_name="injecagent_data_stealing_v1",
        split_override="test_b",
    )
    assert dh_skips == [] and ds_skips == []
    external_parts = [
        (
            "injecagent_direct_harm_v1",
            "InjecAgent",
            "test_b",
            raw_inputs["injecagent_dh"],
            interim / "injecagent_dh_test_b.jsonl",
            dh_rows,
        ),
        (
            "injecagent_data_stealing_v1",
            "InjecAgent",
            "test_b",
            raw_inputs["injecagent_ds"],
            interim / "injecagent_ds_test_b.jsonl",
            ds_rows,
        ),
    ]
    for offset, key in enumerate(("notinject_one", "notinject_two", "notinject_three"), 3):
        _write_parquet_records(
            raw_inputs[key],
            [
                {
                    "id": f"notinject_{offset:04d}",
                    "prompt": _content(10_000 + offset),
                    "word_list": ["synthetic", f"trigger_{offset}"],
                    "category": f"Synthetic category {offset}",
                }
            ],
        )
        notinject_rows, notinject_skips, _ = convert_records(
            raw_inputs[key],
            profile_name="notinject_v1",
            split_override="test_c",
        )
        assert notinject_skips == []
        external_parts.append(
            (
                "notinject_v1",
                "NotInject",
                "test_c",
                raw_inputs[key],
                interim / f"notinject_{key.removeprefix('notinject_')}_test_c.jsonl",
                notinject_rows,
            )
        )

    conversion_specs = [
        (
            "bipia_generated_v1",
            "BIPIA",
            None,
            generated_input,
            interim / "bipia_email_attack_train.canonical.jsonl",
            generated_rows,
        ),
        (
            "bipia_clean_v1",
            "BIPIA",
            None,
            raw_inputs["bipia_context"],
            interim / "bipia_email_clean.canonical.jsonl",
            clean_rows,
        ),
        *external_parts,
    ]
    conversion_report_paths = []
    conversion_outputs: dict[str, list[Path]] = {"test_b": [], "test_c": []}
    for profile, source, split, input_path, output_path, rows in conversion_specs:
        write_jsonl(rows, output_path)
        report_path = output_path.with_suffix(".conversion.json")
        _write_json(
            report_path,
            _conversion_report(
                profile=profile,
                source=source,
                split=split,
                input_path=input_path,
                output_path=output_path,
                rows=rows,
            ),
        )
        conversion_report_paths.append(report_path)
        if split in conversion_outputs:
            conversion_outputs[split].append(output_path)

    registry = yaml.safe_load((ROOT / "configs" / "upstream_sources.yaml").read_text())
    source_rows = []
    for name in ("bipia", "injecagent", "notinject"):
        frozen = registry["sources"][name]
        target = raw_root / name
        source_rows.append(
            {
                "name": name,
                "method": (
                    "huggingface_snapshot"
                    if frozen["kind"] == "huggingface_dataset"
                    else "git"
                ),
                "official_url": frozen["official_url"],
                "revision": frozen["revision"],
                "license_finding": frozen["license"],
                "target": str(target),
                "retrieval_status": "downloaded",
                "files": _inventory(target),
            }
        )
    source_manifest_path = raw_root / "source_manifest.json"
    _write_json(
        source_manifest_path,
        {
            "schema_version": 1,
            "execution_owner": "project_owner",
            "created_at": "2026-08-23T00:00:00+08:00",
            "sources": source_rows,
        },
    )

    builder_report_path = interim / "bipia_email_attack_train.builder.json"
    bipia_revision = registry["sources"]["bipia"]["revision"]
    _write_json(
        builder_report_path,
        {
            "schema_version": 1,
            "status": "reproduced_verified",
            "execution_owner": "project_owner",
            "task": "email",
            "seed": 42,
            "expected_revision": bipia_revision,
            "actual_revision": bipia_revision,
            "source_manifest": {
                "path": str(source_manifest_path),
                "file_sha256": file_sha256(source_manifest_path),
            },
            "contexts": {
                "path": str(raw_inputs["bipia_context"]),
                "size": raw_inputs["bipia_context"].stat().st_size,
                "sha256": file_sha256(raw_inputs["bipia_context"]),
            },
            "attacks": {
                "path": str(raw_inputs["bipia_attacks"]),
                "size": raw_inputs["bipia_attacks"].stat().st_size,
                "sha256": file_sha256(raw_inputs["bipia_attacks"]),
            },
            "output": {
                "path": str(generated_input),
                "rows": len(generated_rows),
                "sha256": file_sha256(generated_input),
            },
            "reproduction": {
                "rows": len(generated_rows),
                "sha256": file_sha256(generated_input),
            },
            "environment": {
                "python": sys.version.split()[0],
                "packages": {
                    "PyYAML": "fixture",
                    "jsonlines": "fixture",
                    "nltk": "fixture",
                    "numpy": "fixture",
                    "pandas": "fixture",
                    "transformers": "fixture",
                },
            },
        },
    )

    merge_output = interim / "bipia_train_pool.unverified.jsonl"
    write_jsonl([*generated_rows, *clean_rows], merge_output)
    merge_report_path = merge_output.with_suffix(".merge.json")
    _write_json(
        merge_report_path,
        {
            "schema_version": 1,
            "status": "merged_unverified",
            "inputs": [
                {
                    "path": str(output_path),
                    "rows": len(rows),
                    "sha256": file_sha256(output_path),
                }
                for _, source, _, _, output_path, rows in conversion_specs
                if source == "BIPIA"
            ],
            "output": str(merge_output),
            "output_sha256": file_sha256(merge_output),
            "rows": len(generated_rows) + len(clean_rows),
            "sources": {"BIPIA": 200},
            "risk_labels": dict(
                sorted(Counter(row.risk_label for row in [*generated_rows, *clean_rows]).items())
            ),
            "human_verified": 0,
        },
    )

    audit_path = reports / "label_audit.csv"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_fields = (*IMMUTABLE_AUDIT_FIELDS, *EDITABLE_AUDIT_FIELDS)
    selected_samples = deterministic_stratified_selection(
        [*generated_rows, *clean_rows],
        requested_size=200,
        seed=AUDIT_SELECTION_SEED,
        grouping=AUDIT_REQUIRED_GROUPING,
    )
    blank_audit_rows = []
    for sample in selected_samples:
        row = sample.model_dump(mode="json")
        row.update(
            audit_status="",
            new_risk_label="",
            new_alignment_label="",
            new_severity="",
            notes="",
            reviewer="",
            reviewed_at="",
        )
        blank_audit_rows.append({field: row.get(field, "") for field in audit_fields})
    with audit_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=audit_fields)
        writer.writeheader()
        writer.writerows(blank_audit_rows)
    initial_audit_hash = file_sha256(audit_path)
    audit_key_path = audit_path.with_suffix(".audit_key.json")
    _write_json(
        audit_key_path,
        {
            "schema_version": 2,
            "selection_algorithm": AUDIT_SELECTION_ALGORITHM,
            "selection_algorithm_version": AUDIT_SELECTION_ALGORITHM_VERSION,
            "seed": AUDIT_SELECTION_SEED,
            "requested_size": 200,
            "selected": 200,
            "input": str(merge_output),
            "input_sha256": file_sha256(merge_output),
            "audit_sheet": str(audit_path),
            "audit_sheet_initial_sha256": initial_audit_hash,
            "sample_ids": [row["sample_id"] for row in blank_audit_rows],
            "required_grouping": list(AUDIT_REQUIRED_GROUPING),
            "immutable_fields": list(IMMUTABLE_AUDIT_FIELDS),
            "immutable_row_sha256": {
                sample.sample_id: audit_row_digest(sample.model_dump(mode="json"))
                for sample in selected_samples
            },
        },
    )
    completed_audit_rows = []
    for row in blank_audit_rows:
        completed = dict(row)
        completed.update(
            audit_status="correct",
            reviewer="synthetic_owner",
            reviewed_at="2026-08-23",
        )
        completed_audit_rows.append(completed)
    with audit_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=audit_fields)
        writer.writeheader()
        writer.writerows(completed_audit_rows)

    audit_summary = summarize(completed_audit_rows, minimum_rows=200)
    audit_summary.update(
        {
            "audit_sheet": str(audit_path),
            "audit_sheet_sha256": file_sha256(audit_path),
            "audit_key": str(audit_key_path),
            "audit_key_sha256": file_sha256(audit_key_path),
            "audited_input": str(merge_output),
            "audited_input_sha256": file_sha256(merge_output),
        }
    )
    audit_summary_path = reports / "label_audit_summary.json"
    _write_json(audit_summary_path, audit_summary)

    audited_rows, replayed_application = apply_audit(
        [*generated_rows, *clean_rows], completed_audit_rows, minimum_rows=200
    )
    audited_output = interim / "bipia_train_pool.audited.jsonl"
    write_jsonl(audited_rows, audited_output)
    audit_application = {
        **audit_summary,
        "application_counts": replayed_application["application_counts"],
        "input": str(merge_output),
        "input_sha256": file_sha256(merge_output),
        "audit": str(audit_path),
        "audit_sha256": file_sha256(audit_path),
        "audit_key": str(audit_key_path),
        "audit_key_sha256": file_sha256(audit_key_path),
        "output": str(audited_output),
        "output_sha256": file_sha256(audited_output),
    }
    audit_application_path = reports / "label_audit_application.json"
    _write_json(audit_application_path, audit_application)

    deduplication = deduplicate_samples(audited_rows, near_threshold=0.92)
    assigned, split_manifest = group_aware_split(deduplication.kept, seed=42)
    fixed_samples: list[IntentSample] = []
    fixed_inputs: dict[str, list[dict[str, Any]]] = {}
    for split, paths in conversion_outputs.items():
        for path in paths:
            rows = read_jsonl(path)
            fixed_samples.extend(rows)
            fixed_inputs.setdefault(split, []).append(
                {"path": str(path), "rows": len(rows), "sha256": file_sha256(path)}
            )
    split_manifest.update(
        {
            "input_summary": dataset_summary(audited_rows),
            "primary_input": {
                "path": str(audited_output),
                "rows": len(audited_rows),
                "sha256": file_sha256(audited_output),
            },
            "deduplication": {
                "kept": len(deduplication.kept),
                "exact_duplicates": deduplication.exact_duplicates,
                "near_duplicates": deduplication.near_duplicates,
                "near_threshold": 0.92,
            },
            "fixed_inputs": fixed_inputs,
        }
    )
    for split in ("test_b", "test_c"):
        rows = [row for row in fixed_samples if row.split == split]
        split_manifest["counts"][split] = {
            "total": len(rows),
            "by_risk": dataset_summary(rows)["risk_labels"],
        }
    final_manifest = write_split_dataset(
        [*assigned, *fixed_samples],
        split_manifest,
        processed,
        expected_splits=C1_REQUIRED_SPLITS,
    )
    split_manifest_path = processed / "split_manifest.json"
    split_paths = {split: processed / f"{split}.jsonl" for split in C1_REQUIRED_SPLITS}
    all_split_rows = [
        row for split in C1_REQUIRED_SPLITS for row in read_jsonl(split_paths[split])
    ]
    context_audit = audit_partition_integrity(all_split_rows, near_threshold=0.92)
    assert context_audit.errors == []
    manifest_evidence = {
        "path": str(split_manifest_path),
        "file_sha256": file_sha256(split_manifest_path),
        "sealed_sha256": final_manifest["sha256"],
    }
    config_path = ROOT / "configs" / "data_pipeline.yaml"
    config_evidence = {
        "path": str(config_path),
        "file_sha256": file_sha256(config_path),
    }
    context_integrity_path = reports / "context_integrity.json"
    _write_json(
        context_integrity_path,
        {
            "status": "passed",
            "errors": [],
            "warnings": context_audit.warnings,
            "summary": context_audit.summary,
            "input_mode": "context",
            "inputs": _input_evidence(split_paths),
            "near_threshold": 0.92,
            "near_duplicate_check_performed": True,
            "manifest": manifest_evidence,
            "config": config_evidence,
        },
    )

    config = yaml.safe_load(config_path.read_text())
    external_paths = {split: split_paths[split] for split in ("test_b", "test_c")}
    external_rows = [
        row for split in external_paths for row in read_jsonl(external_paths[split])
    ]
    external_audit = audit_partition_integrity(
        external_rows,
        near_threshold=0.92,
        require_action_splits=set(external_paths),
        action_policy=config["action_evidence_policy"],
    )
    assert external_audit.errors == []
    external_action_integrity_path = reports / "external_action_integrity.json"
    _write_json(
        external_action_integrity_path,
        {
            "status": "passed",
            "errors": [],
            "warnings": external_audit.warnings,
            "summary": external_audit.summary,
            "input_mode": "action",
            "inputs": _input_evidence(external_paths),
            "near_threshold": 0.92,
            "near_duplicate_check_performed": True,
            "manifest": manifest_evidence,
            "config": config_evidence,
        },
    )

    statistics_output = reports / "dataset_statistics.json"
    label_report_output = reports / "label_quality_report.md"
    data_card_output = reports / "data_card.md"
    argv = ["build_dataset_reports.py", "--manifest", str(split_manifest_path)]
    for split in C1_REQUIRED_SPLITS:
        argv.extend(("--input", f"{split}={split_paths[split]}"))
    argv.extend(
        (
            "--source-manifest",
            str(source_manifest_path),
            "--builder-report",
            str(builder_report_path),
        )
    )
    for report_path in conversion_report_paths:
        argv.extend(("--conversion-report", str(report_path)))
    argv.extend(
        (
            "--merge-report",
            str(merge_report_path),
            "--audit-key",
            str(audit_key_path),
            "--audit-summary",
            str(audit_summary_path),
            "--audit-application",
            str(audit_application_path),
            "--context-integrity",
            str(context_integrity_path),
            "--external-action-integrity",
            str(external_action_integrity_path),
            "--config",
            str(config_path),
            "--statistics-output",
            str(statistics_output),
            "--label-report-output",
            str(label_report_output),
            "--data-card-output",
            str(data_card_output),
        )
    )
    return {
        "argv": argv,
        "audit_application": audit_application_path,
        "audit_key": audit_key_path,
        "audit_sheet": audit_path,
        "audit_summary": audit_summary_path,
        "audited_output": audited_output,
        "conversion_reports": conversion_report_paths,
        "builder_report": builder_report_path,
        "context_integrity": context_integrity_path,
        "external_action_integrity": external_action_integrity_path,
        "manifest": split_manifest_path,
        "merge_output": merge_output,
        "merge_report": merge_report_path,
        "split_paths": split_paths,
        "config": config_path,
        "statistics_output": statistics_output,
        "label_report_output": label_report_output,
        "data_card_output": data_card_output,
    }


def test_label_statistics_expose_redundancy_and_training_blockers() -> None:
    samples = {
        split: [_row(index + 10, split)]
        for index, split in enumerate(C1_REQUIRED_SPLITS)
    }
    samples["train"].append(
        _row(99, "train", risk_label="instruction_hijacking")
    )
    samples["test_b"] = [
        _row(
            20,
            "test_b",
            source="InjecAgent",
            risk_label="tool_manipulation",
            action="SendMessage()",
            action_provenance="benchmark_target",
        )
    ]
    samples["test_c"] = [
        _row(
            21,
            "test_c",
            source="NotInject",
            action="return_text_response()",
            action_provenance="protocol_wrapper",
        )
    ]
    action_policy = {
        split: {
            "sources": ["BIPIA"],
            "allowed_provenance": [],
            "evidence_scope": "blocked",
        }
        for split in ("train", "validation", "calibration", "test_a")
    }
    action_policy.update(
        {
            "test_b": {
                "sources": ["InjecAgent"],
                "allowed_provenance": ["benchmark_target"],
                "evidence_scope": "target",
            },
            "test_c": {
                "sources": ["NotInject"],
                "allowed_provenance": ["protocol_wrapper"],
                "evidence_scope": "wrapper",
            },
        }
    )

    report = compute_label_statistics(samples, action_policy)

    relationship = report["risk_alignment"]
    assert relationship["scope"] == "train_only"
    assert relationship["rows"] == 2
    assert relationship["mutual_information_bits"] == pytest.approx(1.0)
    assert relationship["mi_fraction_of_alignment_entropy"] == pytest.approx(1.0)
    assert relationship["alignment_is_deterministic_from_risk"] is True
    readiness = report["training_readiness"]
    assert readiness["binary_attack_train_class_coverage_present"] is True
    assert readiness["five_class_train_class_coverage_present"] is False
    assert readiness["missing_train_risk_labels"] == [
        "data_exfiltration",
        "privilege_escalation",
        "tool_manipulation",
    ]
    assert readiness["model_c_action_data_ready"] is False


def test_dataset_reports_accept_complete_bound_synthetic_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    evidence = _build_synthetic_evidence_chain(tmp_path)
    monkeypatch.setattr(sys, "argv", evidence["argv"])

    build_dataset_reports_main()

    statistics = json.loads(evidence["statistics_output"].read_text(encoding="utf-8"))
    assert statistics["evidence_status"] == "validated"
    assert statistics["risk_alignment"]["scope"] == "train_only"
    assert statistics["training_readiness"]["model_c_action_data_ready"] is False
    assert evidence["label_report_output"].is_file()
    assert evidence["data_card_output"].is_file()


def test_dataset_reports_reject_canonical_rows_not_matching_adapter_replay(
    tmp_path: Path, monkeypatch
) -> None:
    evidence = _build_synthetic_evidence_chain(tmp_path)
    report_path = next(
        path
        for path in evidence["conversion_reports"]
        if json.loads(path.read_text(encoding="utf-8"))["adapter_profile"]
        == "injecagent_data_stealing_v1"
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    output_path = Path(report["output"])
    rows = read_jsonl(output_path)
    rows[0] = rows[0].model_copy(
        update={"untrusted_content": "tampered canonical content with unchanged metadata"}
    )
    write_jsonl(rows, output_path)
    report["output_sha256"] = file_sha256(output_path)
    _write_json(report_path, report)
    monkeypatch.setattr(sys, "argv", evidence["argv"])

    with pytest.raises(ValueError, match="deterministic adapter replay"):
        build_dataset_reports_main()

    assert not evidence["statistics_output"].exists()


def test_dataset_reports_reject_legacy_audit_key_even_when_hashes_are_refreshed(
    tmp_path: Path, monkeypatch
) -> None:
    evidence = _build_synthetic_evidence_chain(tmp_path)
    key = json.loads(evidence["audit_key"].read_text(encoding="utf-8"))
    key["schema_version"] = 1
    _write_json(evidence["audit_key"], key)
    key_hash = file_sha256(evidence["audit_key"])
    for report_name in ("audit_summary", "audit_application"):
        report_path = evidence[report_name]
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["audit_key_sha256"] = key_hash
        _write_json(report_path, report)
    monkeypatch.setattr(sys, "argv", evidence["argv"])

    with pytest.raises(ValueError, match="schema_version must be 2"):
        build_dataset_reports_main()

    assert not evidence["statistics_output"].exists()


def test_dataset_reports_reject_audit_summary_not_matching_replay(
    tmp_path: Path, monkeypatch
) -> None:
    evidence = _build_synthetic_evidence_chain(tmp_path)
    summary = json.loads(evidence["audit_summary"].read_text(encoding="utf-8"))
    summary["reviewer_counts"] = {"invented_reviewer": 200}
    _write_json(evidence["audit_summary"], summary)
    monkeypatch.setattr(sys, "argv", evidence["argv"])

    with pytest.raises(ValueError, match="audit summary reviewer_counts"):
        build_dataset_reports_main()

    assert not evidence["statistics_output"].exists()


def test_dataset_reports_reject_audited_output_not_matching_application_replay(
    tmp_path: Path, monkeypatch
) -> None:
    evidence = _build_synthetic_evidence_chain(tmp_path)
    rows = read_jsonl(evidence["audited_output"])
    rows[0] = rows[0].model_copy(update={"human_verified": False})
    write_jsonl(rows, evidence["audited_output"])
    application = json.loads(
        evidence["audit_application"].read_text(encoding="utf-8")
    )
    application["output_sha256"] = file_sha256(evidence["audited_output"])
    _write_json(evidence["audit_application"], application)
    monkeypatch.setattr(sys, "argv", evidence["argv"])

    with pytest.raises(ValueError, match="audit application replay"):
        build_dataset_reports_main()

    assert not evidence["statistics_output"].exists()


def test_dataset_reports_accept_legal_primary_duplicate_after_replayed_dedup(
    tmp_path: Path, monkeypatch
) -> None:
    evidence = _build_synthetic_evidence_chain(
        tmp_path, with_primary_exact_duplicate=True
    )
    manifest = json.loads(evidence["manifest"].read_text(encoding="utf-8"))
    monkeypatch.setattr(sys, "argv", evidence["argv"])

    build_dataset_reports_main()

    assert manifest["deduplication"]["kept"] == 199
    assert len(manifest["deduplication"]["exact_duplicates"]) == 1
    assert evidence["statistics_output"].is_file()


def test_dataset_reports_reject_tampered_merge_multiset_with_refreshed_report(
    tmp_path: Path, monkeypatch
) -> None:
    evidence = _build_synthetic_evidence_chain(tmp_path)
    merge_rows = read_jsonl(evidence["merge_output"])[1:]
    write_jsonl(merge_rows, evidence["merge_output"])
    merge_report = json.loads(evidence["merge_report"].read_text(encoding="utf-8"))
    merge_report.update(
        {
            "output_sha256": file_sha256(evidence["merge_output"]),
            "rows": len(merge_rows),
            "sources": dict(sorted(Counter(row.source for row in merge_rows).items())),
            "risk_labels": dict(
                sorted(Counter(row.risk_label for row in merge_rows).items())
            ),
            "human_verified": sum(row.human_verified for row in merge_rows),
        }
    )
    _write_json(evidence["merge_report"], merge_report)
    monkeypatch.setattr(sys, "argv", evidence["argv"])

    with pytest.raises(ValueError, match="merge output sample multiset"):
        build_dataset_reports_main()

    assert not evidence["statistics_output"].exists()


def test_split_lineage_accepts_exact_synthetic_multisets(tmp_path: Path) -> None:
    evidence = _build_synthetic_evidence_chain(tmp_path)
    samples_by_split = {
        split: read_jsonl(evidence["split_paths"][split])
        for split in C1_REQUIRED_SPLITS
    }
    conversion_reports = [
        (path, json.loads(path.read_text(encoding="utf-8")))
        for path in evidence["conversion_reports"]
    ]
    audit_application = json.loads(
        evidence["audit_application"].read_text(encoding="utf-8")
    )
    pipeline_config = yaml.safe_load(evidence["config"].read_text(encoding="utf-8"))
    split_manifest = json.loads(evidence["manifest"].read_text(encoding="utf-8"))

    assert (
        _validate_split_lineage(
            samples_by_split=samples_by_split,
            conversion_reports=conversion_reports,
            audit_application=audit_application,
            pipeline_config=pipeline_config,
            split_manifest=split_manifest,
        )
        == []
    )


@pytest.mark.parametrize(
    ("tampered_split", "expected_error"),
    [
        ("train", "train does not exactly match the replayed deterministic split"),
        ("test_b", "test_b does not exactly equal"),
    ],
)
def test_split_lineage_rejects_one_tampered_row(
    tmp_path: Path, tampered_split: str, expected_error: str
) -> None:
    evidence = _build_synthetic_evidence_chain(tmp_path)
    samples_by_split = {
        split: read_jsonl(evidence["split_paths"][split])
        for split in C1_REQUIRED_SPLITS
    }
    original = samples_by_split[tampered_split][0]
    samples_by_split[tampered_split][0] = original.model_copy(
        update={
            "sample_id": f"tampered_{original.sample_id}",
            "untrusted_content": f"tampered lineage content for {tampered_split}",
        }
    )
    conversion_reports = [
        (path, json.loads(path.read_text(encoding="utf-8")))
        for path in evidence["conversion_reports"]
    ]
    audit_application = json.loads(
        evidence["audit_application"].read_text(encoding="utf-8")
    )
    pipeline_config = yaml.safe_load(evidence["config"].read_text(encoding="utf-8"))
    split_manifest = json.loads(evidence["manifest"].read_text(encoding="utf-8"))

    errors = _validate_split_lineage(
        samples_by_split=samples_by_split,
        conversion_reports=conversion_reports,
        audit_application=audit_application,
        pipeline_config=pipeline_config,
        split_manifest=split_manifest,
    )

    assert any(expected_error in error for error in errors)


def test_split_lineage_rejects_role_swap_that_preserves_primary_union(
    tmp_path: Path,
) -> None:
    evidence = _build_synthetic_evidence_chain(tmp_path)
    samples_by_split = {
        split: read_jsonl(evidence["split_paths"][split])
        for split in C1_REQUIRED_SPLITS
    }
    train_row = samples_by_split["train"][0]
    test_a_row = samples_by_split["test_a"][0]
    samples_by_split["train"][0] = test_a_row.model_copy(update={"split": "train"})
    samples_by_split["test_a"][0] = train_row.model_copy(update={"split": "test_a"})
    conversion_reports = [
        (path, json.loads(path.read_text(encoding="utf-8")))
        for path in evidence["conversion_reports"]
    ]
    audit_application = json.loads(
        evidence["audit_application"].read_text(encoding="utf-8")
    )
    pipeline_config = yaml.safe_load(evidence["config"].read_text(encoding="utf-8"))
    split_manifest = json.loads(evidence["manifest"].read_text(encoding="utf-8"))

    errors = _validate_split_lineage(
        samples_by_split=samples_by_split,
        conversion_reports=conversion_reports,
        audit_application=audit_application,
        pipeline_config=pipeline_config,
        split_manifest=split_manifest,
    )

    assert any("does not exactly match the replayed deterministic split" in error for error in errors)


def test_split_lineage_rejects_tampered_deduplication_evidence(tmp_path: Path) -> None:
    evidence = _build_synthetic_evidence_chain(
        tmp_path, with_primary_exact_duplicate=True
    )
    samples_by_split = {
        split: read_jsonl(evidence["split_paths"][split])
        for split in C1_REQUIRED_SPLITS
    }
    conversion_reports = [
        (path, json.loads(path.read_text(encoding="utf-8")))
        for path in evidence["conversion_reports"]
    ]
    audit_application = json.loads(
        evidence["audit_application"].read_text(encoding="utf-8")
    )
    pipeline_config = yaml.safe_load(evidence["config"].read_text(encoding="utf-8"))
    split_manifest = json.loads(evidence["manifest"].read_text(encoding="utf-8"))
    split_manifest["deduplication"]["exact_duplicates"] = []

    errors = _validate_split_lineage(
        samples_by_split=samples_by_split,
        conversion_reports=conversion_reports,
        audit_application=audit_application,
        pipeline_config=pipeline_config,
        split_manifest=split_manifest,
    )

    assert "split manifest deduplication exact_duplicates does not match replay" in errors


def test_dataset_reports_reject_duplicate_conversion_output(
    tmp_path: Path, monkeypatch
) -> None:
    evidence = _build_synthetic_evidence_chain(tmp_path)
    first = json.loads(evidence["conversion_reports"][0].read_text(encoding="utf-8"))
    duplicate_path = evidence["conversion_reports"][1]
    duplicate = json.loads(duplicate_path.read_text(encoding="utf-8"))
    duplicate["output"] = first["output"]
    duplicate["output_sha256"] = first["output_sha256"]
    _write_json(duplicate_path, duplicate)
    monkeypatch.setattr(sys, "argv", evidence["argv"])

    with pytest.raises(ValueError, match="conversion"):
        build_dataset_reports_main()

    assert not evidence["statistics_output"].exists()


def test_dataset_reports_reports_null_conversion_counter_as_evidence_error(
    tmp_path: Path, monkeypatch
) -> None:
    evidence = _build_synthetic_evidence_chain(tmp_path)
    report_path = evidence["conversion_reports"][2]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["action_provenance"] = None
    _write_json(report_path, report)
    monkeypatch.setattr(sys, "argv", evidence["argv"])

    with pytest.raises(ValueError, match="action provenance"):
        build_dataset_reports_main()

    assert not evidence["statistics_output"].exists()


def test_dataset_reports_reject_duplicate_conversion_input(
    tmp_path: Path, monkeypatch
) -> None:
    evidence = _build_synthetic_evidence_chain(tmp_path)
    first = json.loads(evidence["conversion_reports"][0].read_text(encoding="utf-8"))
    duplicate_path = evidence["conversion_reports"][1]
    duplicate = json.loads(duplicate_path.read_text(encoding="utf-8"))
    duplicate["input"] = first["input"]
    duplicate["input_sha256"] = first["input_sha256"]
    _write_json(duplicate_path, duplicate)
    monkeypatch.setattr(sys, "argv", evidence["argv"])

    with pytest.raises(ValueError, match="same input"):
        build_dataset_reports_main()

    assert not evidence["statistics_output"].exists()


def test_dataset_reports_reject_conversion_input_outside_frozen_source_paths(
    tmp_path: Path, monkeypatch
) -> None:
    evidence = _build_synthetic_evidence_chain(tmp_path)
    report_path = next(
        path
        for path in evidence["conversion_reports"]
        if json.loads(path.read_text(encoding="utf-8"))["adapter_profile"]
        == "injecagent_direct_harm_v1"
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    unregistered_input = tmp_path / "not_in_frozen_source_inventory.json"
    _write_mock_rows(unregistered_input, 1)
    report["input"] = str(unregistered_input)
    report["input_sha256"] = file_sha256(unregistered_input)
    _write_json(report_path, report)
    monkeypatch.setattr(sys, "argv", evidence["argv"])

    with pytest.raises(ValueError, match="frozen source paths|source-manifest inventory"):
        build_dataset_reports_main()

    assert not evidence["statistics_output"].exists()


def test_dataset_reports_reject_conversion_count_not_matching_output_rows(
    tmp_path: Path, monkeypatch
) -> None:
    evidence = _build_synthetic_evidence_chain(tmp_path)
    report_path = next(
        path
        for path in evidence["conversion_reports"]
        if json.loads(path.read_text(encoding="utf-8"))["adapter_profile"]
        == "injecagent_direct_harm_v1"
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    claimed_rows = report["converted"] + 1
    report.update(
        converted=claimed_rows,
        records_read=claimed_rows,
        action_provenance={"benchmark_target": claimed_rows},
        risk_labels={"tool_manipulation": claimed_rows},
    )
    _write_json(report_path, report)
    monkeypatch.setattr(sys, "argv", evidence["argv"])

    with pytest.raises(ValueError, match="output row count does not match report"):
        build_dataset_reports_main()

    assert not evidence["statistics_output"].exists()


def test_dataset_reports_reject_duplicate_conversion_report_path(
    tmp_path: Path, monkeypatch
) -> None:
    evidence = _build_synthetic_evidence_chain(tmp_path)
    report_arguments = [
        index + 1
        for index, argument in enumerate(evidence["argv"])
        if argument == "--conversion-report"
    ]
    evidence["argv"][report_arguments[1]] = evidence["argv"][report_arguments[0]]
    monkeypatch.setattr(sys, "argv", evidence["argv"])

    with pytest.raises(ValueError, match="paths must be unique"):
        build_dataset_reports_main()

    assert not evidence["statistics_output"].exists()


def test_dataset_reports_reject_audit_key_hash_mismatch(
    tmp_path: Path, monkeypatch
) -> None:
    evidence = _build_synthetic_evidence_chain(tmp_path)
    audit_key = json.loads(evidence["audit_key"].read_text(encoding="utf-8"))
    audit_key["tampered_after_reports"] = True
    _write_json(evidence["audit_key"], audit_key)
    monkeypatch.setattr(sys, "argv", evidence["argv"])

    with pytest.raises(ValueError, match="same sheet/key hashes"):
        build_dataset_reports_main()

    assert not evidence["statistics_output"].exists()


def test_dataset_reports_reject_builder_output_not_bound_to_conversion(
    tmp_path: Path, monkeypatch
) -> None:
    evidence = _build_synthetic_evidence_chain(tmp_path)
    builder = json.loads(evidence["builder_report"].read_text(encoding="utf-8"))
    builder["output"]["sha256"] = "0" * 64
    _write_json(evidence["builder_report"], builder)
    monkeypatch.setattr(sys, "argv", evidence["argv"])

    with pytest.raises(ValueError, match="builder output"):
        build_dataset_reports_main()

    assert not evidence["statistics_output"].exists()


def test_dataset_reports_reject_integrity_report_not_bound_to_manifest(
    tmp_path: Path, monkeypatch
) -> None:
    evidence = _build_synthetic_evidence_chain(tmp_path)
    context = json.loads(evidence["context_integrity"].read_text(encoding="utf-8"))
    context["manifest"]["sealed_sha256"] = "0" * 64
    _write_json(evidence["context_integrity"], context)
    monkeypatch.setattr(sys, "argv", evidence["argv"])

    with pytest.raises(ValueError, match="context integrity|sealed manifest"):
        build_dataset_reports_main()

    assert not evidence["statistics_output"].exists()


def test_dataset_reports_reject_skipped_near_duplicate_check(
    tmp_path: Path, monkeypatch
) -> None:
    evidence = _build_synthetic_evidence_chain(tmp_path)
    context = json.loads(evidence["context_integrity"].read_text(encoding="utf-8"))
    context["near_duplicate_check_performed"] = False
    _write_json(evidence["context_integrity"], context)
    monkeypatch.setattr(sys, "argv", evidence["argv"])

    with pytest.raises(ValueError, match="context integrity|full check|near duplicate"):
        build_dataset_reports_main()

    assert not evidence["statistics_output"].exists()
