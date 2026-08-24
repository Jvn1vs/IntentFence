from __future__ import annotations

import csv
import json
from copy import deepcopy
from pathlib import Path

from intentfence.route_b_audit import build_blind_audit_package, select_blind_audit_rows
from intentfence.route_b_corpus import build_formal_mock_records, load_mock_corpus_spec
from intentfence.schema import write_jsonl

ROOT = Path(__file__).resolve().parents[1]


def _small_records():
    spec = deepcopy(load_mock_corpus_spec(ROOT / "configs" / "route_b_mock_corpus.yaml"))
    for role in spec["roles"].values():
        role["template_groups"] = 2
    records, _ = build_formal_mock_records(spec)
    return records


def test_blind_selection_is_stratified_and_deterministic() -> None:
    rows = [row for role_rows in _small_records().values() for row in role_rows]
    first = select_blind_audit_rows(rows, risk_rows=40, alignment_rows=80, seed=42)
    second = select_blind_audit_rows(rows, risk_rows=40, alignment_rows=80, seed=42)
    assert [[row.sample_id for row in group] for group in first] == [
        [row.sample_id for row in group] for group in second
    ]
    assert len(first[0]) == 40
    assert len(first[1]) == 80


def test_audit_package_hides_seed_labels_and_preserves_sealed_truth(tmp_path: Path) -> None:
    records = _small_records()
    paths = []
    for role, rows in records.items():
        path = tmp_path / f"{role}.jsonl"
        write_jsonl(rows, path)
        paths.append(path)
    result = build_blind_audit_package(
        paths,
        tmp_path / "audit",
        risk_rows=40,
        alignment_rows=80,
    )
    manifest = result["manifest"]
    assert manifest["formal_training_authorized"] is False
    assert manifest["reviewer_slots"] == ["reviewer_a", "reviewer_b"]
    with (tmp_path / "audit" / "reviewer_a_risk.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert rows and "risk_label" not in rows[0]
    assert all(not row["risk_label_review"] for row in rows)
    truth = json.loads(
        (tmp_path / "audit" / "sealed_seed_labels.json").read_text(encoding="utf-8")
    )
    assert len(truth["risk"]) == 40
    assert len(truth["alignment"]) == 80
