"""Deterministic, grouped public-source candidate construction (no training)."""

from __future__ import annotations

import hashlib
import math
import unicodedata
from collections import Counter, defaultdict
from typing import Any

from intentfence.schema import IntentSample


def norm(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def shingles(text: str, width: int) -> set[str]:
    text = norm(text)
    return {text[i : i + width] for i in range(max(1, len(text) - width + 1))}


def near(a: set[str], b: set[str], threshold: float) -> bool:
    if min(len(a), len(b)) < threshold * max(len(a), len(b)):
        return False
    return len(a & b) >= threshold * len(a | b)


class SimilarityIndex:
    """Exact Jaccard candidate retrieval by globally ordered prefix filtering."""

    def __init__(self, texts: list[str], width: int, threshold: float):
        self.width, self.threshold = width, threshold
        self.sets = [shingles(text, width) for text in texts]
        self.frequency = Counter(token for values in self.sets for token in values)
        self.postings: dict[str, list[int]] = defaultdict(list)
        for i, values in enumerate(self.sets):
            for token in self.prefix(values):
                self.postings[token].append(i)

    def prefix(self, values: set[str]) -> list[str]:
        ordered = sorted(values, key=lambda token: (self.frequency[token], token))
        return ordered[: len(values) - math.ceil(self.threshold * len(values)) + 1]

    def matches(self, text: str) -> list[int]:
        values = shingles(text, self.width)
        candidates = {i for token in self.prefix(values) for i in self.postings.get(token, [])}
        return [i for i in sorted(candidates) if near(values, self.sets[i], self.threshold)]


def components(texts: list[str], width: int, threshold: float) -> list[str]:
    """Transitive near-duplicate components, independent of input order."""
    unique = sorted({norm(text) for text in texts})
    parent = list(range(len(unique)))
    index = SimilarityIndex(unique, width, threshold)

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, text in enumerate(unique):
        for j in index.matches(text):
            if j < i:
                x, y = find(i), find(j)
                parent[max(x, y)] = min(x, y)
    keys = {text: digest(unique[find(i)]) for i, text in enumerate(unique)}
    return [keys[norm(text)] for text in texts]


def allocate(keys: list[str], ratios: dict[str, float], seed: int) -> dict[str, str]:
    if any(value <= 0 for value in ratios.values()) or not math.isclose(sum(ratios.values()), 1):
        raise ValueError("Split ratios must be positive and sum to one")
    ordered = sorted(set(keys), key=lambda key: digest(f"{seed}:{key}"))
    if len(ordered) < len(ratios):
        raise ValueError("Insufficient independent groups for all splits")
    roles = list(ratios)
    counts = {role: 1 for role in roles}
    for _ in range(len(ordered) - len(roles)):
        role = max(roles, key=lambda role: ratios[role] * len(ordered) - counts[role])
        counts[role] += 1
    result = {}
    offset = 0
    for role in roles:
        for key in ordered[offset : offset + counts[role]]:
            result[key] = role
        offset += counts[role]
    return result


def build(
    contexts: list[dict[str, Any]],
    attacks: dict[str, list[str]],
    hard_negatives: list[dict[str, Any]],
    locked_texts: list[str],
    excluded_families: set[str],
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    width = config["shingle_chars"]
    threshold = config["near_duplicate_jaccard"]
    if width < 1 or not 0 < threshold <= 1 or config["attacks_per_context"] < 1:
        raise ValueError("Invalid deduplication or sampling configuration")
    ratios, seed = config["split_ratios"], config["seed"]
    locked_index = SimilarityIndex(
        [text for text in sorted(set(locked_texts)) if norm(text)], width, threshold
    )

    def blocked(text: str) -> bool:
        return bool(locked_index.matches(text))

    usable_attacks = {
        family: [text for text in values if not blocked(text)]
        for family, values in attacks.items()
        if norm(family) not in excluded_families
    }
    usable_attacks = {family: values for family, values in usable_attacks.items() if values}
    # Near-duplicate attack text links whole families into one indivisible group.
    flat = [(family, text) for family, values in usable_attacks.items() for text in values]
    attack_groups = components([text for _, text in flat], width, threshold)
    family_links = {
        family: {
            group for (name, _), group in zip(flat, attack_groups, strict=True) if name == family
        }
        for family in usable_attacks
    }
    merged = []
    for family in sorted(family_links):
        names, links = {family}, set(family_links[family])
        remaining = []
        for old_names, old_links in merged:
            if links & old_links:
                names |= old_names
                links |= old_links
            else:
                remaining.append((old_names, old_links))
        merged = remaining + [(names, links)]
    family_group = {
        family: digest("|".join(sorted(names))) for names, _ in merged for family in names
    }
    family_roles = allocate(list(family_group.values()), ratios, seed)
    roles_to_attacks = defaultdict(list)
    for family, values in usable_attacks.items():
        for text in values:
            roles_to_attacks[family_roles[family_group[family]]].append((family, text))

    rows = [dict(row, kind="clean") for row in contexts]
    rows += [dict(row, kind="hard_negative", task="authored") for row in hard_negatives]
    seen = set()
    retained = []
    excluded = Counter()
    for row in rows:
        key = digest(norm(row["goal"]) + "\n" + norm(row["content"]))
        if key in seen:
            excluded["duplicate_goal_content"] += 1
        elif blocked(row["content"]):
            excluded["locked_content_overlap"] += 1
        else:
            seen.add(key)
            retained.append(row)
    groups = components([row["content"] for row in retained], width, threshold)
    assignments = allocate(groups, ratios, seed)
    output = []
    rejected_generated = 0
    for row, group in zip(retained, groups, strict=True):
        role = assignments[group]
        variants = [(row["kind"], row["content"], None, None)]
        if row["kind"] == "clean":
            options = sorted(
                roles_to_attacks[role],
                key=lambda pair: digest(f"{seed}:{row['source_record']}:{pair[0]}:{pair[1]}"),
            )
            for index, (family, text) in enumerate(options[: config["attacks_per_context"]]):
                # Project-derived deterministic insertion; not an official builder export.
                position = "start" if index % 2 == 0 else "end"
                content = (
                    text + "\n\n" + row["content"]
                    if position == "start"
                    else row["content"] + "\n\n" + text
                )
                variants.append(("attack", content, family, position))
        for kind, content, family, position in variants:
            if blocked(content):
                rejected_generated += 1
                continue
            attack = kind == "attack"
            sample = IntentSample(
                sample_id="c9_" + digest(row["goal"].strip() + "\n" + content.strip()),
                source="project_owned" if row["task"] == "authored" else "BIPIA",
                scenario=row["task"],
                user_goal=row["goal"],
                untrusted_content=content,
                risk_label="instruction_hijacking" if attack else "benign",
                alignment_label=int(attack),
                task_alignment_label=None,
                severity=3 if attack else 0,
                template_group=group,
                split=role,
                attack_family=family or "none",
                source_record_id=row["source_record"],
                adapter_profile="candidate9_project_derived_v1",
                adapter_missing_action=True,
                action_provenance="missing",
                human_verified=False,
                label_provenance="codex_provisional_mapping_requires_review",
                construction_kind=kind,
                insertion_position=position,
                attack_family_group=family_group[family] if family else None,
                source_attribution=row.get("attribution", "BIPIA pinned train source"),
            )
            output.append(sample.model_dump())
    output.sort(key=lambda row: row["sample_id"])
    if len({row["sample_id"] for row in output}) != len(output):
        raise ValueError("Duplicate generated sample ids")
    final_groups = components([row["untrusted_content"] for row in output], width, threshold)
    group_roles: dict[str, set[str]] = defaultdict(set)
    for row, key in zip(output, final_groups, strict=True):
        group_roles[key].add(row["split"])
    cross_split = sum(len(roles) > 1 for roles in group_roles.values())
    if cross_split:
        raise ValueError(f"Generated near-duplicate groups cross splits: {cross_split}")
    stats = {
        "excluded_backgrounds": dict(excluded),
        "rejected_generated": rejected_generated,
        "background_groups": len(set(groups)),
        "attack_family_groups": len(set(family_group.values())),
        "attack_family_roles": {
            family: family_roles[group] for family, group in family_group.items()
        },
        "splits": {
            role: dict(Counter(row["construction_kind"] for row in output if row["split"] == role))
            for role in ratios
        },
        "training_ready": False,
        "generated_cross_split_near_duplicate_groups": cross_split,
        "limitations": [
            "Provisional risk labels; no independent four-class Alignment labels or actions",
            "Only benign and instruction_hijacking risk labels; five-class coverage incomplete",
            "BIPIA is the only public training source; no independent source holdout",
            "Character-shingle isolation does not prove semantic independence",
        ],
    }
    for role, counts in stats["splits"].items():
        if not counts.get("attack") or not counts.get("clean"):
            raise ValueError(f"Missing positive/negative class in {role}")
    return output, stats
