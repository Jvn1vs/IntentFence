from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from apply_label_audit import apply_audit  # noqa: E402
from apply_label_audit import main as apply_label_audit_main  # noqa: E402
from audit_labels import main as audit_labels_main  # noqa: E402
from build_splits import main as build_splits_main  # noqa: E402
from merge_canonical import main as merge_canonical_main  # noqa: E402
from summarize_label_audit import (  # noqa: E402
    AUDIT_REQUIRED_GROUPING,
    AUDIT_SELECTION_ALGORITHM,
    AUDIT_SELECTION_ALGORITHM_VERSION,
    AUDIT_SELECTION_SEED,
    deterministic_stratified_selection,
    summarize,
    validate_audit_key,
)
from summarize_label_audit import main as summarize_label_audit_main  # noqa: E402
from validate_c1_framework import validate  # noqa: E402
from validate_dataset import main as validate_dataset_main  # noqa: E402

from baselines.evaluate_scores import evaluate_frozen_threshold  # noqa: E402
from intentfence.data import file_sha256  # noqa: E402
from intentfence.schema import IntentSample, read_jsonl, write_jsonl  # noqa: E402


def test_c1_framework_contract_is_valid() -> None:
    assert validate() == []


def test_audit_summary_requires_completed_provenance() -> None:
    rows = [
        {
            "sample_id": "one",
            "source": "BIPIA",
            "action_provenance": "missing",
            "risk_label": "benign",
            "audit_status": "correct",
            "new_risk_label": "",
            "new_alignment_label": "",
            "new_severity": "",
            "reviewer": "owner",
            "reviewed_at": "2026-08-20",
        },
        {
            "sample_id": "two",
            "source": "InjecAgent",
            "action_provenance": "benchmark_target",
            "risk_label": "tool_manipulation",
            "audit_status": "incorrect",
            "new_risk_label": "data_exfiltration",
            "new_alignment_label": "1",
            "new_severity": "4",
            "notes": "risk category corrected after review",
            "reviewer": "owner",
            "reviewed_at": "2026-08-20",
        },
    ]

    report = summarize(rows, minimum_rows=2)

    assert report["status"] == "passed"
    assert report["status_counts"] == {"correct": 1, "incorrect": 1}
    assert report["risk_corrections"][0]["to"] == "data_exfiltration"


def test_validated_audit_correction_is_applied() -> None:
    sample = IntentSample(
        sample_id="one",
        source="test",
        user_goal="read",
        untrusted_content="external text",
        proposed_action="send()",
        risk_label="tool_manipulation",
        alignment_label=1,
        severity=3,
        template_group="g1",
    )
    rows = [
        {
            "sample_id": "one",
            "source": "test",
            "action_provenance": "source_field",
            "risk_label": "tool_manipulation",
            "audit_status": "incorrect",
            "new_risk_label": "data_exfiltration",
            "new_alignment_label": "1",
            "new_severity": "4",
            "notes": "risk category corrected after review",
            "reviewer": "owner",
            "reviewed_at": "2026-08-20",
        }
    ]

    output, report = apply_audit([sample], rows, minimum_rows=1)

    assert output[0].risk_label == "data_exfiltration"
    assert output[0].human_verified is True
    assert output[0].label_provenance == "user_audit_correction"
    assert report["application_counts"] == {"corrected": 1}


def test_audit_summary_rejects_incomplete_review() -> None:
    report = summarize(
        [
            {
                "audit_status": "correct",
                "reviewer": "",
                "reviewed_at": "",
                "source": "BIPIA",
                "action_provenance": "missing",
            }
        ],
        minimum_rows=2,
    )

    assert report["status"] == "failed"
    assert any("reviewer and reviewed_at" in error for error in report["errors"])
    assert any("completed audit rows" in error for error in report["errors"])


def test_audit_summary_rejects_invalid_correction_values() -> None:
    report = summarize(
        [
            {
                "audit_status": "incorrect",
                "reviewer": "owner",
                "reviewed_at": "2026-08-23",
                "source": "BIPIA",
                "action_provenance": "missing",
                "risk_label": "instruction_hijacking",
                "new_risk_label": "benign",
                "new_alignment_label": "1",
                "new_severity": "4",
                "notes": "benign correction values are intentionally inconsistent",
            }
        ],
        minimum_rows=1,
    )

    assert report["status"] == "failed"
    assert any("benign correction requires new_alignment_label=0" in error for error in report["errors"])
    assert any("benign correction requires new_severity<=1" in error for error in report["errors"])


def test_audit_summary_requires_notes_for_nontrivial_decisions() -> None:
    report = summarize(
        [
            {
                "audit_status": "ambiguous",
                "reviewer": "owner",
                "reviewed_at": "2026-08-23",
                "source": "BIPIA",
                "scenario": "email",
                "action_provenance": "missing",
                "notes": "",
            }
        ],
        minimum_rows=1,
    )

    assert report["status"] == "failed"
    assert any("require notes" in error for error in report["errors"])


def test_audit_sheet_refuses_to_overwrite_existing_review(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "label_audit.csv"
    output.write_text("reviewed content\n", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "audit_labels.py",
            "--input",
            str(tmp_path / "unused.jsonl"),
            "--output",
            str(output),
        ],
    )

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        audit_labels_main()


def test_audit_sheet_rejects_non_frozen_seed_before_reading(
    tmp_path: Path, monkeypatch
) -> None:
    output = tmp_path / "label_audit.csv"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "audit_labels.py",
            "--input",
            str(tmp_path / "unused.jsonl"),
            "--output",
            str(output),
            "--seed",
            "41",
        ],
    )

    with pytest.raises(ValueError, match="frozen C1 audit seed 42"):
        audit_labels_main()

    assert not output.exists()


def test_failed_audit_summary_does_not_reserve_the_formal_output(
    tmp_path: Path, monkeypatch
) -> None:
    audit_sheet = tmp_path / "label_audit.csv"
    audit_key = tmp_path / "label_audit.audit_key.json"
    summary = tmp_path / "label_audit_summary.json"
    fields = [
        "sample_id",
        "source",
        "scenario",
        "action_provenance",
        "risk_label",
        "audit_status",
        "reviewer",
        "reviewed_at",
        "notes",
    ]
    with audit_sheet.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "sample_id": "sample_1",
                "source": "BIPIA",
                "scenario": "email",
                "action_provenance": "missing",
                "risk_label": "benign",
                "audit_status": "correct",
                "reviewer": "",
                "reviewed_at": "",
                "notes": "",
            }
        )
    audit_key.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "selected": 1,
                "sample_ids": ["sample_1"],
                "input": str(tmp_path / "input.jsonl"),
                "input_sha256": "0" * 64,
                "audit_sheet": str(audit_sheet),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "summarize_label_audit.py",
            "--input",
            str(audit_sheet),
            "--audit-key",
            str(audit_key),
            "--output",
            str(summary),
            "--minimum-rows",
            "1",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        summarize_label_audit_main()

    assert exc_info.value.code == 1
    assert not summary.exists()


def _create_completed_single_row_audit(
    tmp_path: Path, monkeypatch
) -> tuple[Path, Path, Path]:
    canonical = tmp_path / "canonical.jsonl"
    audit_sheet = tmp_path / "label_audit.csv"
    sample = IntentSample(
        sample_id="review_one",
        source="BIPIA",
        scenario="email",
        user_goal="summarize the message",
        untrusted_content="ordinary review content",
        risk_label="benign",
        alignment_label=0,
        severity=0,
        template_group="review_group",
        adapter_profile="bipia_clean_v1",
        adapter_missing_action=True,
        action_provenance="missing",
    )
    write_jsonl([sample], canonical)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "audit_labels.py",
            "--input",
            str(canonical),
            "--output",
            str(audit_sheet),
            "--size",
            "1",
        ],
    )
    audit_labels_main()
    return canonical, audit_sheet, audit_sheet.with_suffix(".audit_key.json")


def test_audit_key_rejects_non_v2_schema(tmp_path: Path, monkeypatch) -> None:
    _, audit_sheet, audit_key = _create_completed_single_row_audit(tmp_path, monkeypatch)
    key = json.loads(audit_key.read_text(encoding="utf-8"))
    key["schema_version"] = 1
    audit_key.write_text(json.dumps(key), encoding="utf-8")
    with audit_sheet.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    _, errors = validate_audit_key(audit_key, audit_sheet, rows)

    assert "audit key schema_version must be 2" in errors


def test_audit_key_rejects_sample_order_that_cannot_be_replayed(
    tmp_path: Path, monkeypatch
) -> None:
    canonical = tmp_path / "canonical.jsonl"
    audit_sheet = tmp_path / "label_audit.csv"
    samples = [
        IntentSample(
            sample_id=f"replay_{index}",
            source="BIPIA",
            scenario="email",
            user_goal=f"summarize message {index}",
            untrusted_content=f"unique review content {index}",
            risk_label="benign" if index % 2 == 0 else "instruction_hijacking",
            alignment_label=0 if index % 2 == 0 else 1,
            severity=0 if index % 2 == 0 else 3,
            template_group=f"replay_group_{index}",
            adapter_profile=(
                "bipia_clean_v1" if index % 2 == 0 else "bipia_generated_v1"
            ),
            adapter_missing_action=True,
            action_provenance="missing",
        )
        for index in range(4)
    ]
    write_jsonl(samples, canonical)
    forward = deterministic_stratified_selection(
        samples,
        requested_size=4,
        seed=AUDIT_SELECTION_SEED,
        grouping=AUDIT_REQUIRED_GROUPING,
    )
    reversed_input = deterministic_stratified_selection(
        list(reversed(samples)),
        requested_size=4,
        seed=AUDIT_SELECTION_SEED,
        grouping=AUDIT_REQUIRED_GROUPING,
    )
    assert [row.sample_id for row in forward] == [
        row.sample_id for row in reversed_input
    ]
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "audit_labels.py",
            "--input",
            str(canonical),
            "--output",
            str(audit_sheet),
            "--size",
            "4",
        ],
    )
    audit_labels_main()
    audit_key = audit_sheet.with_suffix(".audit_key.json")
    key = json.loads(audit_key.read_text(encoding="utf-8"))
    key["sample_ids"] = list(reversed(key["sample_ids"]))
    audit_key.write_text(json.dumps(key), encoding="utf-8")
    with audit_sheet.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fieldnames = list(rows[0])
    rows.reverse()
    with audit_sheet.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    _, errors = validate_audit_key(audit_key, audit_sheet, rows)

    assert "audit key sample_ids do not match deterministic selection replay" in errors


def test_audit_summary_rejects_tampered_review_content(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    _, audit_sheet, audit_key = _create_completed_single_row_audit(tmp_path, monkeypatch)
    with audit_sheet.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fieldnames = list(rows[0])
    rows[0].update(
        untrusted_content="content substituted after audit sampling",
        audit_status="correct",
        reviewer="owner",
        reviewed_at="2026-08-23",
    )
    with audit_sheet.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    summary = tmp_path / "summary.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "summarize_label_audit.py",
            "--input",
            str(audit_sheet),
            "--audit-key",
            str(audit_key),
            "--output",
            str(summary),
            "--minimum-rows",
            "1",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        summarize_label_audit_main()

    assert exc_info.value.code == 1
    assert "audit sheet immutable fields changed: review_one" in capsys.readouterr().out
    assert not summary.exists()


def test_apply_audit_rejects_tampered_review_label(tmp_path: Path, monkeypatch) -> None:
    canonical, audit_sheet, audit_key = _create_completed_single_row_audit(
        tmp_path, monkeypatch
    )
    with audit_sheet.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fieldnames = list(rows[0])
    rows[0].update(
        risk_label="instruction_hijacking",
        audit_status="correct",
        reviewer="owner",
        reviewed_at="2026-08-23",
    )
    with audit_sheet.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    output = tmp_path / "audited.jsonl"
    report = tmp_path / "application.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "apply_label_audit.py",
            "--input",
            str(canonical),
            "--audit",
            str(audit_sheet),
            "--audit-key",
            str(audit_key),
            "--output",
            str(output),
            "--report",
            str(report),
            "--minimum-rows",
            "1",
        ],
    )

    with pytest.raises(ValueError, match="audit sheet immutable fields changed"):
        apply_label_audit_main()

    assert not output.exists()
    assert not report.exists()


def test_merge_audit_and_application_evidence_hash_chain(
    tmp_path: Path, monkeypatch
) -> None:
    clean = tmp_path / "clean.jsonl"
    attack = tmp_path / "attack.jsonl"
    merged = tmp_path / "merged.jsonl"
    merge_report = tmp_path / "merge_report.json"
    audit_sheet = tmp_path / "label_audit.csv"
    audit_summary = tmp_path / "label_audit_summary.json"
    audited = tmp_path / "audited.jsonl"
    application_report = tmp_path / "application.json"
    clean_row = IntentSample(
        sample_id="clean",
        source="BIPIA",
        user_goal="read email",
        untrusted_content="ordinary message",
        risk_label="benign",
        alignment_label=0,
        severity=0,
        template_group="clean_group",
        adapter_missing_action=True,
        action_provenance="missing",
    )
    attack_row = clean_row.model_copy(
        update={
            "sample_id": "attack",
            "untrusted_content": "ignore the task",
            "risk_label": "instruction_hijacking",
            "alignment_label": 1,
            "severity": 3,
            "template_group": "attack_group",
        }
    )
    write_jsonl([clean_row], clean)
    write_jsonl([attack_row], attack)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "merge_canonical.py",
            "--input",
            str(clean),
            "--input",
            str(attack),
            "--output",
            str(merged),
            "--report",
            str(merge_report),
        ],
    )
    merge_canonical_main()
    merge_payload = json.loads(merge_report.read_text(encoding="utf-8"))
    assert merge_payload["output_sha256"] == file_sha256(merged)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "audit_labels.py",
            "--input",
            str(merged),
            "--output",
            str(audit_sheet),
            "--size",
            "2",
        ],
    )
    audit_labels_main()
    key_path = audit_sheet.with_suffix(".audit_key.json")
    key = json.loads(key_path.read_text(encoding="utf-8"))
    assert key["schema_version"] == 2
    assert key["selection_algorithm"] == AUDIT_SELECTION_ALGORITHM
    assert key["selection_algorithm_version"] == AUDIT_SELECTION_ALGORITHM_VERSION
    assert key["seed"] == AUDIT_SELECTION_SEED
    assert key["required_grouping"] == list(AUDIT_REQUIRED_GROUPING)
    assert key["input_sha256"] == file_sha256(merged)
    assert "severity" in key["immutable_fields"]
    assert set(key["immutable_row_sha256"]) == {"attack", "clean"}

    with audit_sheet.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fieldnames = list(rows[0])
    for row in rows:
        row.update(audit_status="correct", reviewer="owner", reviewed_at="2026-08-23")
    with audit_sheet.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "summarize_label_audit.py",
            "--input",
            str(audit_sheet),
            "--output",
            str(audit_summary),
            "--minimum-rows",
            "2",
        ],
    )
    summarize_label_audit_main()
    summary_payload = json.loads(audit_summary.read_text(encoding="utf-8"))
    assert summary_payload["audit_sheet_sha256"] == file_sha256(audit_sheet)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "apply_label_audit.py",
            "--input",
            str(merged),
            "--audit",
            str(audit_sheet),
            "--output",
            str(audited),
            "--report",
            str(application_report),
            "--minimum-rows",
            "2",
        ],
    )
    apply_label_audit_main()
    application = json.loads(application_report.read_text(encoding="utf-8"))
    assert application["input_sha256"] == merge_payload["output_sha256"]
    assert application["audit_sha256"] == summary_payload["audit_sheet_sha256"]
    assert application["output_sha256"] == file_sha256(audited)


def test_build_splits_integrates_fixed_external_roles(tmp_path: Path, monkeypatch) -> None:
    train_pool = tmp_path / "train_pool.jsonl"
    test_b = tmp_path / "test_b_part.jsonl"
    test_c = tmp_path / "test_c_part.jsonl"
    output_dir = tmp_path / "processed"
    train_samples = [
        IntentSample(
            sample_id=f"train_{index}",
            source="BIPIA",
            user_goal="summarize",
            untrusted_content=f"unique source content number {index}",
            risk_label="benign" if index % 2 == 0 else "instruction_hijacking",
            alignment_label=index % 2,
            severity=0 if index % 2 == 0 else 3,
            template_group=f"train_group_{index}",
            adapter_missing_action=True,
            action_provenance="missing",
        )
        for index in range(8)
    ]
    fixed_b = train_samples[0].model_copy(
        update={
            "sample_id": "fixed_b",
            "source": "InjecAgent",
            "untrusted_content": "unique external attack b",
            "proposed_action": "send_message()",
            "risk_label": "tool_manipulation",
            "alignment_label": 1,
            "severity": 3,
            "template_group": "fixed_group_b",
            "split": "test_b",
            "adapter_missing_action": False,
            "action_provenance": "benchmark_target",
        }
    )
    fixed_c = train_samples[0].model_copy(
        update={
            "sample_id": "fixed_c",
            "source": "NotInject",
            "untrusted_content": "unique external benign c",
            "proposed_action": "return_text_response()",
            "risk_label": "benign",
            "alignment_label": 0,
            "severity": 0,
            "template_group": "fixed_group_c",
            "split": "test_c",
            "adapter_missing_action": False,
            "action_provenance": "protocol_wrapper",
        }
    )
    write_jsonl(train_samples, train_pool)
    write_jsonl([fixed_b], test_b)
    write_jsonl([fixed_c], test_c)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_splits.py",
            "--input",
            str(train_pool),
            "--fixed-input",
            f"test_b={test_b}",
            "--fixed-input",
            f"test_c={test_c}",
            "--output-dir",
            str(output_dir),
            "--near-threshold",
            "1.0",
        ],
    )

    build_splits_main()

    manifest = json.loads((output_dir / "split_manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["files"]) == {
        "train",
        "validation",
        "calibration",
        "test_a",
        "test_b",
        "test_c",
    }
    assert read_jsonl(output_dir / "test_b.jsonl")[0].split == "test_b"
    assert read_jsonl(output_dir / "test_c.jsonl")[0].split == "test_c"


def test_build_splits_rejects_missing_external_role_before_reading(
    tmp_path: Path, monkeypatch
) -> None:
    output_dir = tmp_path / "processed"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_splits.py",
            "--input",
            str(tmp_path / "unused_train.jsonl"),
            "--fixed-input",
            f"test_b={tmp_path / 'unused_test_b.jsonl'}",
            "--output-dir",
            str(output_dir),
        ],
    )

    with pytest.raises(ValueError, match="missing fixed roles: test_c"):
        build_splits_main()

    assert not output_dir.exists()


def test_validate_dataset_rejects_duplicate_input_role_before_reading(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "validate_dataset.py",
            "--input",
            f"test_b={tmp_path / 'first.jsonl'}",
            "--input",
            f"test_b={tmp_path / 'second.jsonl'}",
        ],
    )

    with pytest.raises(ValueError, match="Duplicate --input role: test_b"):
        validate_dataset_main()


def test_validate_dataset_exits_nonzero_for_manifest_only_failure(
    tmp_path: Path, monkeypatch
) -> None:
    dataset = tmp_path / "test_b.jsonl"
    manifest = tmp_path / "split_manifest.json"
    output = tmp_path / "integrity.json"
    sample = IntentSample(
        sample_id="fixed_b",
        source="InjecAgent",
        user_goal="read",
        untrusted_content="unique external content",
        proposed_action="send_message()",
        risk_label="tool_manipulation",
        alignment_label=1,
        severity=3,
        template_group="fixed_b",
        split="test_b",
    )
    write_jsonl([sample], dataset)
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "files": {
                    "test_b": {"path": dataset.name, "rows": 1, "sha256": "0" * 64}
                },
                "sha256": "0" * 64,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "validate_dataset.py",
            "--manifest",
            str(manifest),
            "--input",
            f"test_b={dataset}",
            "--input-mode",
            "action",
            "--output",
            str(output),
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        validate_dataset_main()

    assert exc_info.value.code == 1
    assert not output.exists()


def test_validate_dataset_refuses_to_overwrite_integrity_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    output = tmp_path / "integrity.json"
    output.write_text("sealed evidence\n", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "validate_dataset.py",
            "--input",
            f"test_b={tmp_path / 'unused.jsonl'}",
            "--output",
            str(output),
        ],
    )

    with pytest.raises(FileExistsError, match="Refusing to overwrite integrity report"):
        validate_dataset_main()

    assert output.read_text(encoding="utf-8") == "sealed evidence\n"


def test_action_validation_includes_test_a(tmp_path: Path, monkeypatch) -> None:
    dataset = tmp_path / "test_a.jsonl"
    sample = IntentSample(
        sample_id="bipia_test_a",
        source="BIPIA",
        user_goal="summarize",
        untrusted_content="external content",
        proposed_action="",
        risk_label="instruction_hijacking",
        alignment_label=1,
        severity=3,
        template_group="bipia_test_a",
        split="test_a",
        adapter_missing_action=True,
        action_provenance="missing",
    )
    write_jsonl([sample], dataset)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "validate_dataset.py",
            "--input",
            f"test_a={dataset}",
            "--input-mode",
            "action",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        validate_dataset_main()

    assert exc_info.value.code == 1


def test_external_action_validation_accepts_role_bound_proxy_evidence(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    test_b = tmp_path / "test_b.jsonl"
    test_c = tmp_path / "test_c.jsonl"
    write_jsonl(
        [
            IntentSample(
                sample_id="external_b",
                source="InjecAgent",
                user_goal="handle message",
                untrusted_content="unique external attack",
                proposed_action="SendMessage(target='attacker')",
                risk_label="tool_manipulation",
                alignment_label=1,
                severity=3,
                template_group="external_b",
                split="test_b",
                action_provenance="benchmark_target",
            )
        ],
        test_b,
    )
    write_jsonl(
        [
            IntentSample(
                sample_id="external_c",
                source="NotInject",
                user_goal="answer safely",
                untrusted_content="unique benign request",
                proposed_action="return_text_response()",
                risk_label="benign",
                alignment_label=0,
                severity=0,
                template_group="external_c",
                split="test_c",
                action_provenance="protocol_wrapper",
            )
        ],
        test_c,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "validate_dataset.py",
            "--input",
            f"test_b={test_b}",
            "--input",
            f"test_c={test_c}",
            "--input-mode",
            "action",
            "--skip-near-duplicates",
        ],
    )

    validate_dataset_main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "passed"
    assert payload["config"]["file_sha256"] == file_sha256(
        ROOT / "configs" / "data_pipeline.yaml"
    )
    assert payload["summary"]["action_evidence_scope_by_split"] == {
        "test_b": "benchmark_target_not_observed_agent_output",
        "test_c": "protocol_wrapper_for_overdefense_only",
    }


def test_baseline_threshold_is_selected_from_calibration_only() -> None:
    calibration = [
        {"attack_label": 0, "attack_score": 0.10},
        {"attack_label": 0, "attack_score": 0.20},
        {"attack_label": 1, "attack_score": 0.80},
        {"attack_label": 1, "attack_score": 0.90},
    ]
    test = [
        {"attack_label": 0, "attack_score": 0.95},
        {"attack_label": 1, "attack_score": 0.70},
    ]

    result = evaluate_frozen_threshold(calibration, test, target_fpr=0.01, minimum_tpr=0.80)

    assert result["threshold_source"] == "calibration_only"
    assert result["calibration"]["fpr"] == 0.0
    assert result["calibration"]["tpr"] == 1.0
    assert result["test"]["fpr"] == 1.0
