"""A supplemental must-link may merge but never split prior quarantine groups."""

from __future__ import annotations

import pytest

from scripts.build_aib_family_supplement import extend


def base() -> dict:
    return {
        "components": [["A", "B"], ["C"], ["D", "E"]],
        "source_cases": 5,
        "family_isolation_complete": False,
        "training_ready": False,
        "split": None,
    }


def test_new_link_preserves_previous_components() -> None:
    result = extend(base(), [{"members": ["B", "D"], "reason": "same mechanism"}])
    assert result == [["A", "B", "D", "E"], ["C"]]


@pytest.mark.parametrize("links", [
    [{"members": ["B", "missing"], "reason": "same mechanism"}],
    [{"members": ["B", "B"], "reason": "same mechanism"}],
    [{"members": ["B", "D"], "reason": ""}],
    [],
])
def test_rejects_invalid_supplement(links: list[dict]) -> None:
    with pytest.raises(ValueError):
        extend(base(), links)


def test_rejects_base_graph_that_claims_clearance() -> None:
    record = base()
    record["training_ready"] = True
    with pytest.raises(ValueError, match="quarantined"):
        extend(record, [{"members": ["B", "D"], "reason": "same mechanism"}])
