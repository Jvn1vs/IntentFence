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
    kept: list[IntentSample] = []
    exact_duplicates: list[tuple[str, str]] = []
    near_duplicates: list[tuple[str, str, float]] = []
    fingerprints: dict[str, str] = {}
    ngrams: list[set[str]] = []

    for sample in samples:
        fingerprint = sample_fingerprint(sample)
        if fingerprint in fingerprints:
            exact_duplicates.append((sample.sample_id, fingerprints[fingerprint]))
            continue

        content_signature = char_ngrams(
            "\n".join((sample.user_goal, sample.untrusted_content, sample.proposed_action))
        )
        near_match: tuple[str, float] | None = None
        if detect_near_duplicates:
            for existing, signature in zip(kept, ngrams, strict=True):
                score = jaccard(content_signature, signature)
                if score >= near_threshold:
                    near_match = (existing.sample_id, score)
                    break
        if near_match:
            near_duplicates.append((sample.sample_id, near_match[0], near_match[1]))
            continue

        fingerprints[fingerprint] = sample.sample_id
        kept.append(sample)
        ngrams.append(content_signature)

    return DeduplicationResult(kept, exact_duplicates, near_duplicates)


DEFAULT_SPLIT_RATIOS = {
    "train": 0.70,
    "validation": 0.10,
    "calibration": 0.10,
    "test_a": 0.10,
}


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


def _path_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_split_dataset(
    samples: Iterable[IntentSample], manifest: dict[str, Any], output_dir: str | Path
) -> dict[str, Any]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    buckets: dict[str, list[IntentSample]] = defaultdict(list)
    for sample in samples:
        if sample.split is None:
            raise ValueError(f"Sample {sample.sample_id} does not have a split")
        buckets[sample.split].append(sample)
    files: dict[str, dict[str, Any]] = {}
    for split, split_samples in buckets.items():
        path = destination / f"{split}.jsonl"
        write_jsonl(split_samples, path)
        files[split] = {
            "path": path.name,
            "rows": len(split_samples),
            "sha256": _path_sha256(path),
        }
    final_manifest = seal_manifest({**manifest, "files": dict(sorted(files.items()))})
    (destination / "split_manifest.json").write_text(
        json.dumps(final_manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return final_manifest


def audit_partition_integrity(
    samples: Iterable[IntentSample],
    *,
    near_threshold: float = 0.92,
    check_near_duplicates: bool = True,
    require_action_splits: set[str] | None = None,
) -> DatasetIntegrityReport:
    """Audit IDs, groups, exact content, and optional near duplicates across partitions."""
    records = list(samples)
    errors: list[str] = []
    warnings: list[str] = []
    ids: dict[str, str | None] = {}
    groups: dict[str, str | None] = {}
    fingerprints: dict[str, tuple[str, str | None]] = {}
    missing_actions = Counter()

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

    if check_near_duplicates:
        signatures = [
            char_ngrams("\n".join((row.user_goal, row.untrusted_content, row.proposed_action)))
            for row in records
        ]
        for left_index, left in enumerate(records):
            for right_index in range(left_index + 1, len(records)):
                right = records[right_index]
                if left.split == right.split:
                    continue
                score = jaccard(signatures[left_index], signatures[right_index])
                if score >= near_threshold:
                    errors.append(
                        f"near duplicate crosses splits: {left.sample_id}/{left.split} and "
                        f"{right.sample_id}/{right.split} ({score:.4f})"
                    )

    if missing_actions:
        warnings.append("Rows with missing actions cannot support action-mode evidence.")
    summary = dataset_summary(records)
    summary["by_split"] = dict(sorted(Counter(str(row.split) for row in records).items()))
    summary["missing_actions_by_split"] = dict(sorted(missing_actions.items()))
    summary["action_provenance"] = dict(
        sorted(Counter(row.action_provenance for row in records).items())
    )
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
