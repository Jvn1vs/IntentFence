from __future__ import annotations

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")


def test_c4_materials_keep_missing_evidence_explicit() -> None:
    report = _read("docs/paper_report_template.md")
    matrix = _read("docs/claim_evidence_matrix.md")
    checklist = _read("docs/reproducibility_checklist.md")

    assert "UNVERIFIED" in report
    assert "not-run" in matrix
    assert "claim_id" in matrix
    assert "final-test" in checklist
    assert "Project owner" in checklist


def test_public_cards_state_the_deployment_and_label_boundaries() -> None:
    model_card = _read("docs/model_card.md")
    threat_model = _read("docs/threat_model.md")
    data_card = _read("data/DATASET_CARD.md")

    assert "No trained model" in model_card
    assert all(label in model_card for label in ("aligned", "unrelated", "ambiguous", "malicious"))
    assert "does not replace" in threat_model
    assert "legacy schema" in data_card
