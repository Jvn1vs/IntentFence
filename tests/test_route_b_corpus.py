from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from intentfence.route_b import validate_route_b_samples
from intentfence.route_b_corpus import (
    build_formal_mock_records,
    load_mock_corpus_spec,
    validate_formal_mock_manifest,
    write_formal_mock_corpus,
)

ROOT = Path(__file__).resolve().parents[1]


def _small_spec() -> dict:
    spec = load_mock_corpus_spec(ROOT / "configs" / "route_b_mock_corpus.yaml")
    reduced = deepcopy(spec)
    for role in reduced["roles"].values():
        role["template_groups"] = 1
    return reduced


def test_formal_mock_builder_produces_full_counterfactual_matrix() -> None:
    records, traces = build_formal_mock_records(_small_spec())
    assert {role: len(rows) for role, rows in records.items()} == {
        "train": 100,
        "validation": 100,
        "calibration": 100,
        "test_a": 100,
    }
    assert len(traces) == 400
    assert all(trace["executed"] is False for trace in traces)
    assert all(trace["external_side_effects"] is False for trace in traces)
    for rows in records.values():
        pairs: dict[str, set[str]] = {}
        for row in rows:
            pairs.setdefault(row.action_pair_group, set()).add(row.task_alignment_label)
        assert all(
            labels == {"aligned", "unrelated", "ambiguous", "malicious"}
            for labels in pairs.values()
        )


def test_formal_mock_builder_passes_route_b_structure() -> None:
    records, _ = build_formal_mock_records(_small_spec())
    policy = load_mock_corpus_spec(ROOT / "configs" / "route_b_data_protocol.yaml")
    report = validate_route_b_samples(
        [row for role_rows in records.values() for row in role_rows],
        policy,
    )
    assert report["errors"] == []
    assert report["status"] == "structure_passed_readiness_blocked"
    assert report["summary"]["risk_alignment_mutual_information_bits"] == 0.0


def test_formal_mock_writer_seals_nontraining_manifest(tmp_path: Path) -> None:
    output = tmp_path / "candidate"
    result = write_formal_mock_corpus(_small_spec(), output)
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["formal_training_authorized"] is False
    assert manifest["traces"]["executed"] is False
    assert manifest["traces"]["external_side_effects"] is False
    assert manifest["splits"]["test_a"]["rows"] == 100
    assert validate_formal_mock_manifest(result["manifest_path"]) == []


def test_formal_mock_manifest_detects_changed_split(tmp_path: Path) -> None:
    output = tmp_path / "candidate"
    result = write_formal_mock_corpus(_small_spec(), output)
    with (output / "train.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("{}\n")
    assert "split hash mismatch: train" in validate_formal_mock_manifest(
        result["manifest_path"]
    )
