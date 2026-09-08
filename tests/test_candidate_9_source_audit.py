from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_candidate_9_sources import overlap  # noqa: E402


def test_overlap_rejects_recombined_attack_with_different_user() -> None:
    rows = [{"attack": " ＩＧＮＯＲＥ  instructions ", "user": "new user"}, {"attack": "novel"}]
    tests = [{"attack": "ignore instructions", "user": "old user"}]
    assert overlap(rows, tests, "attack") == {
        "rows": 2, "overlapping_rows": 1, "remaining_rows": 1,
    }


def test_empty_key_fails_closed() -> None:
    with pytest.raises(ValueError, match="Empty isolation key"):
        overlap([{"attack": " "}], [{"attack": "text"}], "attack")
