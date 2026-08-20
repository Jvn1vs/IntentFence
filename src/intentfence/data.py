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
                abs(counts[split][label] + current_group_counts[label] - target)
                / max(target, 1)
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
    manifest_payload = json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode("utf-8")
    manifest["sha256"] = hashlib.sha256(manifest_payload).hexdigest()
    return output, manifest


def write_split_dataset(
    samples: Iterable[IntentSample], manifest: dict[str, Any], output_dir: str | Path
) -> None:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    buckets: dict[str, list[IntentSample]] = defaultdict(list)
    for sample in samples:
        if sample.split is None:
            raise ValueError(f"Sample {sample.sample_id} does not have a split")
        buckets[sample.split].append(sample)
    for split, split_samples in buckets.items():
        write_jsonl(split_samples, destination / f"{split}.jsonl")
    (destination / "split_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


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
