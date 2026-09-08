from __future__ import annotations

import random
import string

import pytest

from intentfence.candidate9 import (
    SimilarityIndex,
    allocate,
    build,
    components,
    digest,
    near,
    shingles,
)


def test_index_matches_exhaustive_jaccard() -> None:
    rng = random.Random(12)
    corpus = ["".join(rng.choices("abcdef", k=30)) for _ in range(100)]
    corpus += [text[:25] + "abcde" for text in corpus[:20]]
    for threshold in (0.4, 0.8, 1.0):
        index = SimilarityIndex(corpus, 3, threshold)
        for query in corpus[::7] + ["new characters not in corpus"]:
            expected = [
                i
                for i, text in enumerate(corpus)
                if near(shingles(query, 3), shingles(text, 3), threshold)
            ]
            assert index.matches(query) == expected


def test_components_transitive_and_order_independent() -> None:
    texts = ["abcd", "abcde", "bcde", "unrelated"]
    groups = components(texts, 1, 0.8)
    assert groups[0] == groups[1] == groups[2] != groups[3]
    assert groups == list(reversed(components(list(reversed(texts)), 1, 0.8)))


def test_allocate_requires_enough_groups() -> None:
    with pytest.raises(ValueError, match="Insufficient"):
        allocate(["same", "same"], {"train": 0.7, "test_a": 0.3}, 42)


def fixture() -> tuple:
    rng = random.Random(7)

    def text() -> str:
        return "".join(rng.choices(string.ascii_letters + " ", k=150))

    contexts = [
        {"goal": text(), "content": text(), "task": "email", "source_record": str(i)}
        for i in range(40)
    ]
    attacks = {f"family{i}": [text()] for i in range(12)}
    hard = [{"goal": text(), "content": text(), "source_record": f"hn{i}"} for i in range(8)]
    config = {
        "seed": 42,
        "split_ratios": {"train": 0.7, "validation": 0.1, "calibration": 0.1, "test_a": 0.1},
        "shingle_chars": 5,
        "near_duplicate_jaccard": 0.8,
        "attacks_per_context": 2,
    }
    return contexts, attacks, hard, config


def test_build_isolates_families_and_preserves_review_boundary() -> None:
    contexts, attacks, hard, config = fixture()
    locked = [contexts[0]["content"]]
    rows, stats = build(contexts, attacks, hard, locked, {"family0"}, config)
    roles = {}
    for row in rows:
        assert not row["human_verified"]
        assert row["task_alignment_label"] is None
        assert row["proposed_action"] == ""
        assert row["attack_family"] != "family0"
        assert row["source_record_id"] != "0"
        if row["attack_family_group"]:
            roles.setdefault(row["attack_family_group"], set()).add(row["split"])
    assert all(len(values) == 1 for values in roles.values())
    assert stats["generated_cross_split_near_duplicate_groups"] == 0
    assert not stats["training_ready"]
    again, _ = build(contexts[::-1], attacks, hard[::-1], locked, {"family0"}, config)
    assert rows == again


def test_no_attack_pool_fails_closed() -> None:
    contexts, _, hard, config = fixture()
    with pytest.raises(ValueError, match="Insufficient"):
        build(contexts, {}, hard, [], set(), config)


def test_ids_bind_serialized_schema_text_after_whitespace_normalization() -> None:
    contexts, attacks, hard, config = fixture()
    for row in contexts:
        row["goal"] = "  " + row["goal"] + "\n"
        row["content"] = "\n" + row["content"] + "  "
    rows, _ = build(contexts, attacks, hard, [], set(), config)
    assert all(
        row["sample_id"] == "c9_" + digest(row["user_goal"] + "\n" + row["untrusted_content"])
        for row in rows
    )
