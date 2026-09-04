from __future__ import annotations

import random
from itertools import combinations

import pytest

import intentfence.data as data_module
from intentfence.data import (
    C1_REQUIRED_SPLITS,
    _exact_jaccard_cross_partition_pairs,
    audit_partition_integrity,
    audit_split_manifest,
    deduplicate_samples,
    group_aware_split,
    sample_fingerprint,
    seal_manifest,
    verify_manifest,
    write_split_dataset,
)
from intentfence.schema import IntentSample
from intentfence.text import char_ngrams, jaccard


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


def _brute_force_deduplicate(
    rows: list[IntentSample],
    *,
    near_threshold: float,
    detect_near_duplicates: bool = True,
) -> tuple[list[str], list[tuple[str, str]], list[tuple[str, str, float]]]:
    kept: list[IntentSample] = []
    exact_duplicates: list[tuple[str, str]] = []
    near_duplicates: list[tuple[str, str, float]] = []
    fingerprints: dict[str, str] = {}
    signatures: list[set[str]] = []

    for row in rows:
        fingerprint = sample_fingerprint(row)
        if fingerprint in fingerprints:
            exact_duplicates.append((row.sample_id, fingerprints[fingerprint]))
            continue
        signature = char_ngrams(
            "\n".join((row.user_goal, row.untrusted_content, row.proposed_action))
        )
        near_match: tuple[str, float] | None = None
        if detect_near_duplicates:
            for existing, existing_signature in zip(kept, signatures, strict=True):
                score = jaccard(signature, existing_signature)
                if score >= near_threshold:
                    near_match = (existing.sample_id, score)
                    break
        if near_match is not None:
            near_duplicates.append((row.sample_id, near_match[0], near_match[1]))
            continue
        fingerprints[fingerprint] = row.sample_id
        kept.append(row)
        signatures.append(signature)

    return (
        [row.sample_id for row in kept],
        exact_duplicates,
        near_duplicates,
    )


def test_exact_deduplication():
    first = sample(1, "a", "same")
    second = sample(2, "b", "same")
    result = deduplicate_samples([first, second])
    assert [item.sample_id for item in result.kept] == ["s1"]
    assert result.exact_duplicates == [("s2", "s1")]


def test_indexed_deduplication_matches_brute_force_random_inputs():
    rng = random.Random(20260823)
    vocabulary = ("alpha", "bravo", "charlie", "delta", "echo", "foxtrot")
    thresholds = (-0.1, 0.0, 0.14, 0.35, 0.5, 0.92, 1.0, 1.01, float("nan"))

    for trial in range(80):
        contents: list[str] = []
        rows: list[IntentSample] = []
        for index in range(rng.randint(2, 30)):
            if contents and rng.random() < 0.25:
                content = rng.choice(contents)
            else:
                content = " ".join(
                    rng.choice(vocabulary) for _ in range(rng.randint(0, 12))
                )
                contents.append(content)
            rows.append(sample(trial * 100 + index, f"random_{trial}_{index}", content))

        threshold = rng.choice(thresholds)
        expected = _brute_force_deduplicate(rows, near_threshold=threshold)
        actual = deduplicate_samples(rows, near_threshold=threshold)

        assert [row.sample_id for row in actual.kept] == expected[0]
        assert actual.exact_duplicates == expected[1]
        assert actual.near_duplicates == expected[2]


def test_indexed_deduplication_preserves_first_kept_match(monkeypatch):
    rows = [
        sample(100, "first", "first-marker"),
        sample(101, "second", "second-marker"),
        sample(102, "candidate", "candidate-marker"),
    ]
    signatures = {
        "first-marker": {"a", "first-common"},
        "second-marker": {"b", "second-common"},
        "candidate-marker": {"a", "first-common", "b", "second-common"},
    }

    def fake_char_ngrams(value: str) -> set[str]:
        return next(signature for marker, signature in signatures.items() if marker in value)

    monkeypatch.setattr(data_module, "char_ngrams", fake_char_ngrams)

    result = deduplicate_samples(rows, near_threshold=0.5)

    assert [row.sample_id for row in result.kept] == ["s100", "s101"]
    assert result.near_duplicates == [("s102", "s100", 0.5)]


def test_indexed_deduplication_handles_exact_float_and_empty_boundaries(monkeypatch):
    large = {f"token_{index}" for index in range(50)}
    boundary = {f"token_{index}" for index in range(43, 50)}

    def fake_char_ngrams(value: str) -> set[str]:
        if "large-marker" in value:
            return large
        if "boundary-marker" in value:
            return boundary
        return set()

    monkeypatch.setattr(data_module, "char_ngrams", fake_char_ngrams)
    rows = [sample(110, "large", "large-marker"), sample(111, "small", "boundary-marker")]

    boundary_result = deduplicate_samples(rows, near_threshold=0.14)
    assert boundary_result.near_duplicates == [("s111", "s110", 0.14)]

    empty = sample(112, "empty", "placeholder").model_copy(
        update={"user_goal": "", "untrusted_content": "", "proposed_action": ""}
    )
    nonempty = sample(113, "nonempty", "large-marker")
    zero_result = deduplicate_samples([empty, nonempty], near_threshold=0.0)
    assert zero_result.near_duplicates == [("s113", "s112", 0.0)]


def test_indexed_deduplication_rejects_nonnumeric_threshold_but_ignores_it_when_disabled():
    rows = [sample(120, "one"), sample(121, "two")]

    with pytest.raises(TypeError, match="near_threshold must be a numeric value"):
        deduplicate_samples(rows, near_threshold="invalid")  # type: ignore[arg-type]

    result = deduplicate_samples(
        rows,
        near_threshold="ignored",  # type: ignore[arg-type]
        detect_near_duplicates=False,
    )
    assert [row.sample_id for row in result.kept] == ["s120", "s121"]


def test_indexed_deduplication_compresses_candidates(monkeypatch):
    rows = [sample(2000 + index, f"rare_{index}") for index in range(120)]
    original_jaccard = data_module.jaccard
    comparison_count = 0

    def rare_first_signature(value: str) -> set[str]:
        return {"shared", value}

    def counting_jaccard(left: set[str], right: set[str]) -> float:
        nonlocal comparison_count
        comparison_count += 1
        return original_jaccard(left, right)

    monkeypatch.setattr(data_module, "char_ngrams", rare_first_signature)
    monkeypatch.setattr(data_module, "jaccard", counting_jaccard)

    result = deduplicate_samples(rows, near_threshold=0.92)

    all_pairs = len(rows) * (len(rows) - 1) // 2
    assert len(result.kept) == len(rows)
    assert comparison_count < all_pairs // 20


def test_group_split_has_no_leakage():
    samples = [sample(index, f"g{index // 2}") for index in range(12)]
    assigned, manifest = group_aware_split(samples, seed=7)
    seen = {}
    for item in assigned:
        previous = seen.setdefault(item.template_group, item.split)
        assert previous == item.split
    assert set(manifest["counts"]) == {"train", "validation", "calibration", "test_a"}
    assert all(value["total"] > 0 for value in manifest["counts"].values())


def test_group_split_manifest_ratios_are_stable_across_float_summation() -> None:
    _, manifest = group_aware_split([sample(index, f"g{index}") for index in range(8)])

    assert manifest["ratios"] == {
        "train": 0.70,
        "validation": 0.10,
        "calibration": 0.10,
        "test_a": 0.10,
    }


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
    assert audit_split_manifest(tmp_path / "split_manifest.json") == []


def test_split_writer_refuses_to_overwrite_existing_outputs(tmp_path):
    assigned, manifest = group_aware_split(
        [sample(index, f"g{index}") for index in range(8)], seed=42
    )
    write_split_dataset(assigned, manifest, tmp_path)

    with pytest.raises(FileExistsError, match="Refusing to overwrite split outputs"):
        write_split_dataset(assigned, manifest, tmp_path)


def test_split_manifest_audit_rejects_modified_output_file(tmp_path):
    assigned, manifest = group_aware_split(
        [sample(index, f"g{index}") for index in range(8)], seed=42
    )
    write_split_dataset(assigned, manifest, tmp_path)
    with (tmp_path / "train.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("{}\n")

    errors = audit_split_manifest(tmp_path / "split_manifest.json")

    assert any("split file hash mismatch" in error for error in errors)
    assert any("split file row count mismatch" in error for error in errors)


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


def test_jaccard_prefix_filter_matches_exhaustive_random_small_sets():
    rng = random.Random(20260823)
    tokens = [f"token_{index}" for index in range(12)]
    thresholds = (0.0, 0.14, 0.35, 0.5, 0.72, 0.92, 1.0, 1.01)

    for _ in range(80):
        signatures = [
            {token for token in tokens if rng.random() < 0.35}
            for _ in range(rng.randint(2, 14))
        ]
        partitions = [rng.choice(("train", "validation", "test_a")) for _ in signatures]
        threshold = rng.choice(thresholds)
        expected = []
        for left, right in combinations(range(len(signatures)), 2):
            if partitions[left] == partitions[right]:
                continue
            score = jaccard(signatures[left], signatures[right])
            if score >= threshold:
                expected.append((left, right, score))

        actual, candidate_count, comparison_count = (
            _exact_jaccard_cross_partition_pairs(signatures, partitions, threshold)
        )

        assert actual == expected
        assert comparison_count <= candidate_count

    large = {f"boundary_{index}" for index in range(50)}
    small = {f"boundary_{index}" for index in range(43, 50)}
    actual, _, _ = _exact_jaccard_cross_partition_pairs(
        [large, small], ["train", "test_a"], 0.14
    )
    assert actual == [(0, 1, 0.14)]


def test_integrity_audit_detects_cross_split_near_duplicate_with_exact_score():
    content = "abcdefghijklmnopqrstuvwxyz" * 8
    left = sample(60, "near_left", content).model_copy(update={"split": "train"})
    right = sample(61, "near_right", content + "x").model_copy(
        update={"split": "test_a"}
    )

    report = audit_partition_integrity([left, right], near_threshold=0.80)

    assert any("near duplicate crosses splits" in error for error in report.errors)
    assert report.summary["near_duplicate_candidate_count"] == 1
    assert report.summary["near_duplicate_comparison_count"] == 1


def test_jaccard_prefix_filter_candidates_are_far_below_all_pairs():
    rows = [
        sample(1000 + index, f"rare_{index}", chr(0x4E00 + index) * 40).model_copy(
            update={"split": "train" if index % 2 == 0 else "test_a"}
        )
        for index in range(120)
    ]

    report = audit_partition_integrity(rows, near_threshold=0.92)

    possible_cross_split_pairs = 60 * 60
    assert report.summary["near_duplicate_candidate_count"] < possible_cross_split_pairs // 20
    assert (
        report.summary["near_duplicate_comparison_count"]
        <= report.summary["near_duplicate_candidate_count"]
    )
    assert not any("near duplicate crosses splits" in error for error in report.errors)


def test_c1_writer_requires_exact_nonempty_roles(tmp_path):
    assigned, manifest = group_aware_split(
        [sample(index, f"g{index}") for index in range(8)], seed=42
    )

    with pytest.raises(ValueError, match="required set"):
        write_split_dataset(
            assigned,
            manifest,
            tmp_path,
            expected_splits=C1_REQUIRED_SPLITS,
        )

    assert list(tmp_path.iterdir()) == []


def test_c1_manifest_requires_six_roles_and_bound_input_paths(tmp_path):
    split_samples = []
    counts = {}
    for index, split in enumerate(C1_REQUIRED_SPLITS):
        row = sample(index + 20, f"manifest_{split}", f"manifest content {split}").model_copy(
            update={"split": split}
        )
        split_samples.append(row)
        counts[split] = {"total": 1, "by_risk": {row.risk_label: 1}}
    final = write_split_dataset(
        split_samples,
        {"schema_version": 1, "counts": counts},
        tmp_path,
        expected_splits=C1_REQUIRED_SPLITS,
    )
    manifest_path = tmp_path / "split_manifest.json"
    supplied = {
        split: tmp_path / entry["path"] for split, entry in final["files"].items()
    }
    copied_train = tmp_path / "copied_train.jsonl"
    copied_train.write_text(
        supplied["train"].read_text(encoding="utf-8"), encoding="utf-8"
    )
    supplied["train"] = copied_train

    errors = audit_split_manifest(
        manifest_path,
        expected_splits=C1_REQUIRED_SPLITS,
        supplied_paths=supplied,
    )

    assert any("does not match manifest path: train" in error for error in errors)


def test_c1_manifest_can_bind_a_declared_subset_while_auditing_all_files(tmp_path):
    split_samples = []
    counts = {}
    for index, split in enumerate(C1_REQUIRED_SPLITS):
        row = sample(index + 40, f"subset_{split}", f"subset content {split}").model_copy(
            update={"split": split}
        )
        split_samples.append(row)
        counts[split] = {"total": 1, "by_risk": {row.risk_label: 1}}
    final = write_split_dataset(
        split_samples,
        {"schema_version": 1, "counts": counts},
        tmp_path,
        expected_splits=C1_REQUIRED_SPLITS,
    )
    supplied = {
        split: tmp_path / final["files"][split]["path"] for split in ("test_b", "test_c")
    }

    errors = audit_split_manifest(
        tmp_path / "split_manifest.json",
        expected_splits=C1_REQUIRED_SPLITS,
        supplied_paths=supplied,
        allow_subset_supplied_paths=True,
    )

    assert errors == []


def test_action_gate_uses_split_source_and_provenance_allowlists():
    policy = {
        "train": {
            "sources": ["BIPIA"],
            "allowed_provenance": [],
            "evidence_scope": "blocked",
        },
        "test_b": {
            "sources": ["InjecAgent"],
            "allowed_provenance": ["benchmark_target"],
            "evidence_scope": "target_only",
        },
        "test_c": {
            "sources": ["NotInject"],
            "allowed_provenance": ["protocol_wrapper"],
            "evidence_scope": "wrapper_only",
        },
    }
    test_b = sample(40, "action_b", "action b").model_copy(
        update={
            "source": "InjecAgent",
            "split": "test_b",
            "action_provenance": "benchmark_target",
        }
    )
    test_c = sample(41, "action_c", "action c").model_copy(
        update={
            "source": "NotInject",
            "split": "test_c",
            "action_provenance": "protocol_wrapper",
        }
    )
    accepted = audit_partition_integrity(
        [test_b, test_c],
        check_near_duplicates=False,
        require_action_splits={"test_b", "test_c"},
        action_policy=policy,
    )

    assert accepted.errors == []
    assert accepted.summary["action_evidence_scope_by_split"] == {
        "test_b": "target_only",
        "test_c": "wrapper_only",
    }

    blocked_train = sample(42, "action_train", "action train").model_copy(
        update={
            "source": "BIPIA",
            "split": "train",
            "action_provenance": "source_field",
        }
    )
    rejected = audit_partition_integrity(
        [blocked_train],
        check_near_duplicates=False,
        require_action_splits={"train"},
        action_policy=policy,
    )

    assert any("unsupported action provenance" in error for error in rejected.errors)


def test_action_gate_rejects_unknown_provenance_even_with_nonempty_action():
    row = sample(50, "unknown_action").model_copy(update={"split": "test_b"})
    report = audit_partition_integrity(
        [row],
        check_near_duplicates=False,
        require_action_splits={"test_b"},
        action_policy={
            "test_b": {
                "sources": ["test"],
                "allowed_provenance": ["benchmark_target"],
                "evidence_scope": "target_only",
            }
        },
    )

    assert any("unsupported action provenance" in error for error in report.errors)
