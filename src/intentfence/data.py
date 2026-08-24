from __future__ import annotations

import hashlib
import json
import random
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from intentfence.schema import IntentSample, write_jsonl
from intentfence.text import char_ngrams, jaccard, normalize_text


def sample_fingerprint(sample: IntentSample) -> str:
    fields = (
        normalize_text(sample.user_goal),
        normalize_text(sample.untrusted_content),
        normalize_text(sample.proposed_action),
    )
    return hashlib.sha256("\x1f".join(fields).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DeduplicationResult:
    kept: list[IntentSample]
    exact_duplicates: list[tuple[str, str]]
    near_duplicates: list[tuple[str, str, float]]


@dataclass(frozen=True)
class DatasetIntegrityReport:
    errors: list[str]
    warnings: list[str]
    summary: dict[str, Any]


def deduplicate_samples(
    samples: Iterable[IntentSample],
    *,
    near_threshold: float = 0.92,
    detect_near_duplicates: bool = True,
) -> DeduplicationResult:
    records = list(samples)
    kept: list[IntentSample] = []
    exact_duplicates: list[tuple[str, str]] = []
    near_duplicates: list[tuple[str, str, float]] = []
    fingerprints: dict[str, str] = {}
    kept_signatures: list[set[str]] = []

    signatures: list[set[str]] = []
    prefixes: list[tuple[str, ...]] = []
    use_prefix_index = False
    if detect_near_duplicates:
        if not isinstance(near_threshold, int | float):
            raise TypeError("near_threshold must be a numeric value")
        signatures = [
            char_ngrams(
                "\n".join(
                    (sample.user_goal, sample.untrusted_content, sample.proposed_action)
                )
            )
            for sample in records
        ]
        use_prefix_index = (
            near_threshold > 0
            and near_threshold <= 1
            and near_threshold == near_threshold
        )
        if use_prefix_index:
            token_frequency = Counter(
                token for signature in signatures for token in signature
            )
            prefixes = [
                _jaccard_prefix_tokens(signature, token_frequency, near_threshold)
                for signature in signatures
            ]

    prefix_index: dict[str, list[int]] = defaultdict(list)
    empty_kept_indices: list[int] = []

    for record_index, sample in enumerate(records):
        fingerprint = sample_fingerprint(sample)
        if fingerprint in fingerprints:
            exact_duplicates.append((sample.sample_id, fingerprints[fingerprint]))
            continue

        content_signature = signatures[record_index] if detect_near_duplicates else set()
        near_match: tuple[str, float] | None = None
        if detect_near_duplicates:
            if near_threshold <= 0:
                candidate_indices: Iterable[int] = range(len(kept))
            elif not use_prefix_index:
                candidate_indices = ()
            elif not content_signature:
                candidate_indices = empty_kept_indices
            else:
                candidates = {
                    kept_index
                    for token in prefixes[record_index]
                    for kept_index in prefix_index[token]
                    if _jaccard_lengths_can_reach_threshold(
                        len(kept_signatures[kept_index]),
                        len(content_signature),
                        near_threshold,
                    )
                }
                candidate_indices = sorted(candidates)

            for kept_index in candidate_indices:
                score = jaccard(content_signature, kept_signatures[kept_index])
                if score >= near_threshold:
                    near_match = (kept[kept_index].sample_id, score)
                    break
        if near_match:
            near_duplicates.append((sample.sample_id, near_match[0], near_match[1]))
            continue

        fingerprints[fingerprint] = sample.sample_id
        kept_index = len(kept)
        kept.append(sample)
        kept_signatures.append(content_signature)
        if use_prefix_index:
            if content_signature:
                for token in prefixes[record_index]:
                    prefix_index[token].append(kept_index)
            else:
                empty_kept_indices.append(kept_index)

    return DeduplicationResult(kept, exact_duplicates, near_duplicates)


DEFAULT_SPLIT_RATIOS = {
    "train": 0.70,
    "validation": 0.10,
    "calibration": 0.10,
    "test_a": 0.10,
}

C1_REQUIRED_SPLITS: tuple[str, ...] = (
    "train",
    "validation",
    "calibration",
    "test_a",
    "test_b",
    "test_c",
)

def group_aware_split(
    samples: Iterable[IntentSample],
    *,
    ratios: dict[str, float] | None = None,
    seed: int = 42,
) -> tuple[list[IntentSample], dict[str, Any]]:
    """Assign whole template groups while approximately preserving label balance."""

    ratios = ratios or DEFAULT_SPLIT_RATIOS
    if not ratios or any(value <= 0 for value in ratios.values()):
        raise ValueError("All split ratios must be positive")
    total_ratio = sum(ratios.values())
    normalized_ratios = {key: value / total_ratio for key, value in ratios.items()}

    groups: dict[str, list[IntentSample]] = defaultdict(list)
    for sample in samples:
        groups[sample.template_group].append(sample)
    if len(groups) < len(ratios):
        raise ValueError(
            f"Need at least {len(ratios)} template groups for {len(ratios)} splits; got {len(groups)}"
        )

    rng = random.Random(seed)
    group_items = list(groups.items())
    rng.shuffle(group_items)
    group_items.sort(key=lambda item: len(item[1]), reverse=True)

    total_by_label = Counter(sample.risk_label for _, group in group_items for sample in group)
    target_size = {
        split: normalized_ratios[split] * sum(total_by_label.values()) for split in ratios
    }
    target_by_label = {
        split: {label: normalized_ratios[split] * count for label, count in total_by_label.items()}
        for split in ratios
    }
    assigned: dict[str, list[IntentSample]] = {split: [] for split in ratios}
    counts: dict[str, Counter[str]] = {split: Counter() for split in ratios}

    # Seed every split with one group to avoid empty calibration/test partitions.
    split_order = list(ratios)
    for split, (_, group) in zip(split_order, group_items[: len(split_order)], strict=True):
        assigned[split].extend(group)
        counts[split].update(sample.risk_label for sample in group)

    for _, group in group_items[len(split_order) :]:
        group_counts = Counter(sample.risk_label for sample in group)
        group_size = len(group)

        def cost(
            split: str,
            current_group_counts: Counter[str] = group_counts,
            current_group_size: int = group_size,
        ) -> tuple[float, float]:
            projected_size = len(assigned[split]) + current_group_size
            size_cost = abs(projected_size - target_size[split]) / max(target_size[split], 1)
            label_cost = sum(
                abs(counts[split][label] + current_group_counts[label] - target) / max(target, 1)
                for label, target in target_by_label[split].items()
            )
            return (label_cost + size_cost, len(assigned[split]))

        chosen = min(ratios, key=cost)
        assigned[chosen].extend(group)
        counts[chosen].update(group_counts)

    output: list[IntentSample] = []
    manifest_groups: dict[str, str] = {}
    for split, split_samples in assigned.items():
        for sample in split_samples:
            manifest_groups[sample.template_group] = split
            output.append(sample.model_copy(update={"split": split}))

    manifest = {
        "schema_version": 1,
        "seed": seed,
        "ratios": normalized_ratios,
        "group_to_split": dict(sorted(manifest_groups.items())),
        "counts": {
            split: {
                "total": len(split_samples),
                "by_risk": dict(sorted(Counter(s.risk_label for s in split_samples).items())),
            }
            for split, split_samples in assigned.items()
        },
    }
    return output, manifest


def seal_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Return a copy whose hash covers every field except the hash itself."""
    sealed = {key: value for key, value in manifest.items() if key != "sha256"}
    payload = json.dumps(sealed, sort_keys=True, ensure_ascii=False).encode("utf-8")
    sealed["sha256"] = hashlib.sha256(payload).hexdigest()
    return sealed


def verify_manifest(manifest: dict[str, Any]) -> bool:
    expected = manifest.get("sha256")
    return isinstance(expected, str) and seal_manifest(manifest)["sha256"] == expected


def file_sha256(path: str | Path) -> str:
    path = Path(path)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_split_manifest(
    manifest_path: str | Path,
    *,
    expected_splits: Iterable[str] | None = None,
    supplied_paths: dict[str, str | Path] | None = None,
    allow_subset_supplied_paths: bool = False,
) -> list[str]:
    """Verify a sealed split manifest and every file it references."""

    source = Path(manifest_path).resolve()
    errors: list[str] = []
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read split manifest {source}: {exc}"]
    if not isinstance(payload, dict):
        return [f"split manifest must contain an object: {source}"]
    if not verify_manifest(payload):
        errors.append("split manifest self-hash is invalid")
    files = payload.get("files")
    if not isinstance(files, dict) or not files:
        errors.append("split manifest files mapping is missing or empty")
        return errors
    if expected_splits is not None:
        required = set(expected_splits)
        present = set(files)
        missing = sorted(required - present)
        unexpected = sorted(present - required)
        if missing:
            errors.append(f"split manifest is missing required roles: {', '.join(missing)}")
        if unexpected:
            errors.append(f"split manifest has unexpected roles: {', '.join(unexpected)}")
    if supplied_paths is not None:
        supplied = set(supplied_paths)
        declared = set(files)
        missing_inputs = sorted(declared - supplied)
        unexpected_inputs = sorted(supplied - declared)
        if missing_inputs and not allow_subset_supplied_paths:
            errors.append(f"validation inputs are missing manifest roles: {', '.join(missing_inputs)}")
        if unexpected_inputs:
            errors.append(
                f"validation inputs contain roles absent from manifest: {', '.join(unexpected_inputs)}"
            )
    counts = payload.get("counts")
    if expected_splits is not None:
        required = set(expected_splits)
        if not isinstance(counts, dict):
            errors.append("split manifest counts mapping is missing or invalid")
        else:
            count_roles = set(counts)
            missing_counts = sorted(required - count_roles)
            unexpected_counts = sorted(count_roles - required)
            if missing_counts:
                errors.append(
                    f"split manifest counts are missing required roles: {', '.join(missing_counts)}"
                )
            if unexpected_counts:
                errors.append(
                    f"split manifest counts have unexpected roles: {', '.join(unexpected_counts)}"
                )
    resolved_paths: dict[Path, str] = {}
    for split, raw_entry in sorted(files.items()):
        if not isinstance(raw_entry, dict):
            errors.append(f"split manifest file entry is invalid: {split}")
            continue
        relative = raw_entry.get("path")
        expected_hash = raw_entry.get("sha256")
        expected_rows = raw_entry.get("rows")
        if not isinstance(relative, str) or not relative:
            errors.append(f"split manifest path is invalid: {split}")
            continue
        path = (source.parent / relative).resolve()
        if path.parent != source.parent:
            errors.append(f"split manifest path escapes output directory: {split}/{relative}")
            continue
        if expected_splits is not None and path.name != f"{split}.jsonl":
            errors.append(f"split manifest path does not match its role: {split}/{relative}")
        previous_split = resolved_paths.setdefault(path, split)
        if previous_split != split:
            errors.append(
                f"multiple split roles reference the same file: {previous_split}, {split}/{relative}"
            )
        if supplied_paths is not None and split in supplied_paths:
            supplied_path = Path(supplied_paths[split]).resolve()
            if supplied_path != path:
                errors.append(
                    f"validation input does not match manifest path: {split} "
                    f"({supplied_path} != {path})"
                )
        if not path.is_file():
            errors.append(f"split file is missing: {split}/{relative}")
            continue
        if not isinstance(expected_hash, str) or file_sha256(path) != expected_hash:
            errors.append(f"split file hash mismatch: {split}/{relative}")
        minimum_rows = 1 if expected_splits is not None else 0
        if type(expected_rows) is not int or expected_rows < minimum_rows:
            errors.append(f"split file row count is invalid: {split}/{relative}")
        else:
            with path.open(encoding="utf-8") as handle:
                actual_rows = sum(bool(line.strip()) for line in handle)
            if actual_rows != expected_rows:
                errors.append(
                    f"split file row count mismatch: {split}/{relative} "
                    f"({actual_rows} != {expected_rows})"
                )
        if isinstance(counts, dict) and split in counts:
            count_entry = counts[split]
            count_total = count_entry.get("total") if isinstance(count_entry, dict) else None
            if type(count_total) is not int or count_total != expected_rows:
                errors.append(
                    f"split manifest count/file rows disagree: {split} "
                    f"({count_total} != {expected_rows})"
                )
    return errors


def write_split_dataset(
    samples: Iterable[IntentSample],
    manifest: dict[str, Any],
    output_dir: str | Path,
    *,
    expected_splits: Iterable[str] | None = None,
) -> dict[str, Any]:
    destination = Path(output_dir)
    buckets: dict[str, list[IntentSample]] = defaultdict(list)
    for sample in samples:
        if sample.split is None:
            raise ValueError(f"Sample {sample.sample_id} does not have a split")
        buckets[sample.split].append(sample)
    required = set(expected_splits) if expected_splits is not None else None
    if required is not None and set(buckets) != required:
        missing = sorted(required - set(buckets))
        unexpected = sorted(set(buckets) - required)
        raise ValueError(
            "split output roles do not match the required set: "
            f"missing={missing}, unexpected={unexpected}"
        )
    if required is not None:
        counts = manifest.get("counts")
        if not isinstance(counts, dict) or set(counts) != required:
            raise ValueError("manifest counts do not exactly match the required split roles")
        for split in sorted(required):
            count_entry = counts[split]
            count_total = count_entry.get("total") if isinstance(count_entry, dict) else None
            if type(count_total) is not int or count_total != len(buckets[split]):
                raise ValueError(
                    f"manifest count does not match split rows: {split} "
                    f"({count_total} != {len(buckets[split])})"
                )
    planned_paths = [destination / f"{split}.jsonl" for split in buckets]
    planned_paths.append(destination / "split_manifest.json")
    if required is not None and destination.is_dir():
        planned_paths.extend(destination.glob("*.jsonl"))
    existing = [path for path in planned_paths if path.exists()]
    if existing:
        rendered = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Refusing to overwrite split outputs: {rendered}")
    destination.mkdir(parents=True, exist_ok=True)
    files: dict[str, dict[str, Any]] = {}
    for split, split_samples in buckets.items():
        path = destination / f"{split}.jsonl"
        write_jsonl(split_samples, path)
        files[split] = {
            "path": path.name,
            "rows": len(split_samples),
            "sha256": file_sha256(path),
        }
    final_manifest = seal_manifest({**manifest, "files": dict(sorted(files.items()))})
    (destination / "split_manifest.json").write_text(
        json.dumps(final_manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return final_manifest


def _minimum_overlap_for_threshold(size: int, threshold: float) -> int:
    """Return the smallest overlap whose float ratio meets ``threshold``."""

    if size <= 0:
        return 0
    estimate = min(size, max(0, int(threshold * size)))
    while estimate > 0 and (estimate - 1) / size >= threshold:
        estimate -= 1
    while estimate <= size and estimate / size < threshold:
        estimate += 1
    return estimate


def _jaccard_lengths_can_reach_threshold(
    left_size: int,
    right_size: int,
    threshold: float,
) -> bool:
    larger = max(left_size, right_size)
    return not larger or min(left_size, right_size) / larger >= threshold


def _jaccard_prefix_tokens(
    signature: set[str],
    token_frequency: Counter[str],
    threshold: float,
) -> tuple[str, ...]:
    ordered = sorted(signature, key=lambda token: (token_frequency[token], token))
    minimum_overlap = _minimum_overlap_for_threshold(len(ordered), threshold)
    prefix_length = min(len(ordered), len(ordered) - minimum_overlap + 1)
    return tuple(ordered[:prefix_length])


def _exact_jaccard_cross_partition_pairs(
    signatures: list[set[str]],
    partitions: list[str | None],
    threshold: float,
) -> tuple[list[tuple[int, int, float]], int, int]:
    """Find exact cross-partition Jaccard matches via lossless prefix filtering.

    Tokens use one deterministic global document-frequency order. Prefix overlap
    and the set-length ratio are only necessary conditions; every surviving pair
    is still scored with the canonical exact ``jaccard`` implementation.
    """

    if len(signatures) != len(partitions):
        raise ValueError("signatures and partitions must have the same length")

    def cross_partition_pairs() -> list[tuple[int, int]]:
        return [
            (left, right)
            for left in range(len(signatures))
            for right in range(left + 1, len(signatures))
            if partitions[left] != partitions[right]
        ]

    if threshold <= 0:
        candidates = cross_partition_pairs()
    elif threshold > 1 or threshold != threshold:
        candidates = []
    else:
        token_frequency = Counter(
            token for signature in signatures for token in signature
        )
        prefix_index: dict[str, list[int]] = defaultdict(list)
        candidate_set: set[tuple[int, int]] = set()
        empty_indices: list[int] = []

        for current, signature in enumerate(signatures):
            if not signature:
                for previous in empty_indices:
                    if (
                        partitions[previous] != partitions[current]
                        and _jaccard_lengths_can_reach_threshold(0, 0, threshold)
                    ):
                        candidate_set.add((previous, current))
                empty_indices.append(current)
                continue

            prefix = _jaccard_prefix_tokens(signature, token_frequency, threshold)
            for token in prefix:
                for previous in prefix_index[token]:
                    if (
                        partitions[previous] != partitions[current]
                        and _jaccard_lengths_can_reach_threshold(
                            len(signatures[previous]), len(signature), threshold
                        )
                    ):
                        candidate_set.add((previous, current))
                prefix_index[token].append(current)
        candidates = sorted(candidate_set)

    matches: list[tuple[int, int, float]] = []
    comparison_count = 0
    for left, right in candidates:
        comparison_count += 1
        score = jaccard(signatures[left], signatures[right])
        if score >= threshold:
            matches.append((left, right, score))
    return matches, len(candidates), comparison_count


def audit_partition_integrity(
    samples: Iterable[IntentSample],
    *,
    near_threshold: float = 0.92,
    check_near_duplicates: bool = True,
    require_action_splits: set[str] | None = None,
    action_policy: dict[str, dict[str, Any]] | None = None,
) -> DatasetIntegrityReport:
    """Audit IDs, groups, exact content, and optional near duplicates across partitions."""
    records = list(samples)
    errors: list[str] = []
    warnings: list[str] = []
    ids: dict[str, str | None] = {}
    groups: dict[str, str | None] = {}
    fingerprints: dict[str, tuple[str, str | None]] = {}
    missing_actions = Counter()
    unsupported_action_provenance = Counter()
    near_duplicate_candidate_count = 0
    near_duplicate_comparison_count = 0

    for sample in records:
        if sample.sample_id in ids:
            errors.append(f"duplicate sample_id: {sample.sample_id}")
        ids[sample.sample_id] = sample.split

        previous_split = groups.setdefault(sample.template_group, sample.split)
        if previous_split != sample.split:
            errors.append(
                f"template_group crosses splits: {sample.template_group} "
                f"({previous_split}, {sample.split})"
            )

        fingerprint = sample_fingerprint(sample)
        if fingerprint in fingerprints:
            other_id, other_split = fingerprints[fingerprint]
            scope = (
                "crosses splits" if other_split != sample.split else "is duplicated within split"
            )
            errors.append(
                f"exact content {scope}: {other_id}/{other_split} and {sample.sample_id}/{sample.split}"
            )
        fingerprints.setdefault(fingerprint, (sample.sample_id, sample.split))

        if sample.adapter_missing_action or not sample.proposed_action:
            missing_actions[str(sample.split)] += 1
            if require_action_splits and sample.split in require_action_splits:
                errors.append(f"action-mode row lacks an action: {sample.sample_id}/{sample.split}")
        elif require_action_splits and sample.split in require_action_splits:
            policy = (action_policy or {}).get(str(sample.split))
            if not isinstance(policy, dict):
                unsupported_action_provenance[str(sample.split)] += 1
                errors.append(
                    f"action-mode split has no evidence policy: {sample.sample_id}/{sample.split}"
                )
            else:
                allowed_sources = set(policy.get("sources", []))
                allowed_provenance = set(policy.get("allowed_provenance", []))
                invalid_action_evidence = False
                if sample.source not in allowed_sources:
                    invalid_action_evidence = True
                    errors.append(
                        "action-mode row has a source incompatible with its split: "
                        f"{sample.sample_id}/{sample.split}/{sample.source}"
                    )
                if sample.action_provenance not in allowed_provenance:
                    invalid_action_evidence = True
                    errors.append(
                        "action-mode row has unsupported action provenance: "
                        f"{sample.sample_id}/{sample.split}/{sample.action_provenance}"
                    )
                if invalid_action_evidence:
                    unsupported_action_provenance[str(sample.split)] += 1

    if check_near_duplicates:
        signatures = [
            char_ngrams("\n".join((row.user_goal, row.untrusted_content, row.proposed_action)))
            for row in records
        ]
        near_matches, near_duplicate_candidate_count, near_duplicate_comparison_count = (
            _exact_jaccard_cross_partition_pairs(
                signatures,
                [row.split for row in records],
                near_threshold,
            )
        )
        for left_index, right_index, score in near_matches:
            left = records[left_index]
            right = records[right_index]
            errors.append(
                f"near duplicate crosses splits: {left.sample_id}/{left.split} and "
                f"{right.sample_id}/{right.split} ({score:.4f})"
            )

    if missing_actions:
        warnings.append("Rows with missing actions cannot support action-mode evidence.")
    if unsupported_action_provenance:
        warnings.append(
            "Rows with unsupported or role-incompatible action provenance cannot support "
            "action-mode evidence."
        )
    summary = dataset_summary(records)
    summary["by_split"] = dict(sorted(Counter(str(row.split) for row in records).items()))
    summary["missing_actions_by_split"] = dict(sorted(missing_actions.items()))
    summary["unsupported_action_provenance_by_split"] = dict(
        sorted(unsupported_action_provenance.items())
    )
    summary["action_provenance"] = dict(
        sorted(Counter(row.action_provenance for row in records).items())
    )
    summary["near_duplicate_candidate_count"] = near_duplicate_candidate_count
    summary["near_duplicate_comparison_count"] = near_duplicate_comparison_count
    summary["action_provenance_by_split"] = {
        split: dict(
            sorted(
                Counter(
                    row.action_provenance for row in records if str(row.split) == split
                ).items()
            )
        )
        for split in sorted({str(row.split) for row in records})
    }
    if action_policy is not None:
        summary["action_evidence_scope_by_split"] = {
            split: action_policy.get(split, {}).get("evidence_scope", "unconfigured")
            for split in sorted({str(row.split) for row in records})
        }
    return DatasetIntegrityReport(errors=errors, warnings=warnings, summary=summary)


def dataset_summary(samples: Iterable[IntentSample]) -> dict[str, Any]:
    records = list(samples)
    lengths = [len(sample.untrusted_content.split()) for sample in records]
    return {
        "total": len(records),
        "sources": dict(sorted(Counter(s.source for s in records).items())),
        "scenarios": dict(sorted(Counter(s.scenario for s in records).items())),
        "risk_labels": dict(sorted(Counter(s.risk_label for s in records).items())),
        "alignment_labels": dict(sorted(Counter(s.alignment_label for s in records).items())),
        "template_groups": len({s.template_group for s in records}),
        "human_verified": sum(s.human_verified for s in records),
        "content_words": {
            "min": min(lengths, default=0),
            "mean": (sum(lengths) / len(lengths)) if lengths else 0,
            "max": max(lengths, default=0),
        },
    }
