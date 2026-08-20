from __future__ import annotations

from intentfence.data import deduplicate_samples, group_aware_split
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
