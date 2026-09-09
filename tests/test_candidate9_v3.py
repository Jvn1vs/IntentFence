from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from verify_candidate_9_v3 import check_dolly_rows  # noqa: E402


def fixture() -> tuple:
    background = {
        "source_record": "databricks/databricks-dolly-15k@revision:1",
        "task": "dolly_closed_qa",
        "goal": " Question? ",
        "content": " reference text ",
        "attribution": "CC-BY-SA-3.0",
    }
    row = {
        "source_record_id": background["source_record"],
        "source": "DatabricksDolly15k",
        "scenario": background["task"],
        "user_goal": "Question?",
        "source_attribution": background["attribution"],
        "construction_kind": "clean",
        "untrusted_content": "reference text",
    }
    return row, [background]


def test_source_reconstruction_checks_clean_and_poisoned_content() -> None:
    row, backgrounds = fixture()
    assert check_dolly_rows([row], backgrounds, {}) == 1
    row.update(
        construction_kind="attack",
        attack_family="family",
        insertion_position="end",
        untrusted_content="reference text \n\nInjected diversion",
    )
    assert check_dolly_rows([row], backgrounds, {"family": ["Injected diversion"]}) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("source", "BIPIA"),
        ("untrusted_content", "Changed source text"),
        ("source_attribution", "Apache-2.0"),
        ("user_goal", "Different task"),
    ],
)
def test_wrong_identity_attribution_or_text_rejected(field: str, value: str) -> None:
    row, backgrounds = fixture()
    row[field] = value
    with pytest.raises(ValueError):
        check_dolly_rows([row], backgrounds, {})
