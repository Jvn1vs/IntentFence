from __future__ import annotations

from intentfence.data import (
    audit_partition_integrity,
    deduplicate_samples,
    group_aware_split,
    seal_manifest,
    verify_manifest,
    write_split_dataset,
)
from intentfence.schema import IntentSample


def sample(index: int, group: str, content: str | None = None) -> IntentSample:
    return IntentSample(
        sample_id=f"s{index}",
        source="test",
        user_goal="summarize",
        untrusted_content=content or f"unique content {index}",
        proposed_action="return_summary()",
        risk_label="benign" if index % 2 == 0 else "instruction_hijacking",
        alignment_label=index % 2,
        severity=0 if index % 2 == 0 else 2,
        template_group=group,
    )


def test_exact_deduplication():
    first = sample(1, "a", "same")
    second = sample(2, "b", "same")
    result = deduplicate_samples([first, second])
    assert [item.sample_id for item in result.kept] == ["s1"]
    assert result.exact_duplicates == [("s2", "s1")]


def test_group_split_has_no_leakage():
    samples = [sample(index, f"g{index // 2}") for index in range(12)]
    assigned, manifest = group_aware_split(samples, seed=7)
    seen = {}
    for item in assigned:
        previous = seen.setdefault(item.template_group, item.split)
        assert previous == item.split
    assert set(manifest["counts"]) == {"train", "validation", "calibration", "test_a"}
    assert all(value["total"] > 0 for value in manifest["counts"].values())


def test_manifest_hash_covers_late_metadata():
    manifest = seal_manifest({"schema_version": 1, "counts": {"train": 3}})
    assert verify_manifest(manifest)
    manifest["counts"]["train"] = 4
    assert not verify_manifest(manifest)


def test_written_split_manifest_covers_output_file_hashes(tmp_path):
    assigned, manifest = group_aware_split(
        [sample(index, f"g{index}") for index in range(8)], seed=42
    )

    final_manifest = write_split_dataset(assigned, manifest, tmp_path)

    assert verify_manifest(final_manifest)
    assert set(final_manifest["files"]) == {"train", "validation", "calibration", "test_a"}
    assert all(len(item["sha256"]) == 64 for item in final_manifest["files"].values())


def test_integrity_audit_rejects_group_leakage_and_missing_action():
    left = sample(1, "shared").model_copy(
        update={"split": "train", "proposed_action": "", "adapter_missing_action": True}
    )
    right = sample(2, "shared").model_copy(update={"split": "test_a"})

    report = audit_partition_integrity(
        [left, right], check_near_duplicates=False, require_action_splits={"train"}
    )

    assert any("template_group crosses splits" in error for error in report.errors)
    assert any("action-mode row lacks an action" in error for error in report.errors)


def test_integrity_audit_rejects_duplicate_content_within_one_split():
    left = sample(1, "g1", "same content").model_copy(update={"split": "train"})
    right = sample(2, "g2", "same content").model_copy(update={"split": "train"})

    report = audit_partition_integrity([left, right], check_near_duplicates=False)

    assert any("exact content is duplicated within split" in error for error in report.errors)
