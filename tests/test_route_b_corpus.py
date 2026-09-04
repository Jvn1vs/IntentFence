from __future__ import annotations

import hashlib
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
    spec = load_mock_corpus_spec(
        ROOT / "configs" / "route_b_mock_corpus_candidate_6.yaml"
    )
    reduced = deepcopy(spec)
    for role in reduced["roles"].values():
        role["template_groups"] = 1
    return reduced


def _small_candidate_7_spec() -> dict:
    spec = load_mock_corpus_spec(
        ROOT / "configs" / "route_b_mock_corpus_candidate_7.yaml"
    )
    reduced = deepcopy(spec)
    for role in reduced["roles"].values():
        role["template_groups"] = 1
    return reduced


def _small_candidate_8_spec() -> dict:
    spec = load_mock_corpus_spec(
        ROOT / "configs" / "route_b_mock_corpus_candidate_8.yaml"
    )
    reduced = deepcopy(spec)
    for role in reduced["roles"].values():
        role["template_groups"] = 10
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
    assert report["summary"]["semantic_template_isolation"] == {
        "enabled": True,
        "normalized_text_templates": 20,
        "normalized_action_templates": 25,
        "text_templates_crossing_roles": 0,
        "action_templates_crossing_roles": 0,
    }


def test_candidate_7_encodes_auditable_risk_and_alignment_remediations() -> None:
    records, _ = build_formal_mock_records(_small_candidate_7_spec())
    rows = [row for role_rows in records.values() for row in role_rows]
    instruction_rows = [row for row in rows if row.risk_label == "instruction_hijacking"]
    manipulation_rows = [row for row in rows if row.risk_label == "tool_manipulation"]
    ambiguous_rows = [row for row in rows if row.task_alignment_label == "ambiguous"]

    assert instruction_rows
    assert all("ignore the user's requested workflow" in row.untrusted_content for row in instruction_rows)
    assert all("tool-target substitution" in row.untrusted_content for row in instruction_rows)
    assert manipulation_rows
    assert all("public object" in row.untrusted_content for row in manipulation_rows)
    assert all("external transfer" in row.untrusted_content for row in manipulation_rows)
    assert ambiguous_rows
    assert all("workflow.request_authorization" in row.proposed_action for row in ambiguous_rows)
    assert all("do not establish whether" in row.proposed_action for row in ambiguous_rows)


def test_candidate_8_replaces_wildcard_ticket_actions_without_mutating_candidate_7() -> None:
    candidate_7_spec = _small_candidate_7_spec()
    for role in candidate_7_spec["roles"].values():
        role["template_groups"] = 10
    candidate_7_records, _ = build_formal_mock_records(candidate_7_spec)
    candidate_8_records, _ = build_formal_mock_records(_small_candidate_8_spec())
    candidate_7_actions = [
        row.proposed_action
        for rows in candidate_7_records.values()
        for row in rows
        if '"tool":"ticket.update"' in row.proposed_action
    ]
    candidate_8_actions = [
        row.proposed_action
        for rows in candidate_8_records.values()
        for row in rows
        if '"tool":"ticket.update"' in row.proposed_action
    ]

    assert any('"ticket_id":"*"' in action for action in candidate_7_actions)
    assert candidate_8_actions
    assert all('"ticket_id":"*"' not in action for action in candidate_8_actions)
    assert all('"ticket_id":"T-' in action or '"ticket_id":"project-OBJ-' in action for action in candidate_8_actions)


def test_candidate_4_is_rejected_by_normalized_template_isolation() -> None:
    spec = load_mock_corpus_spec(ROOT / "configs" / "route_b_mock_corpus.yaml")
    reduced = deepcopy(spec)
    for role in reduced["roles"].values():
        role["template_groups"] = 1
    records, _ = build_formal_mock_records(reduced)
    policy = load_mock_corpus_spec(ROOT / "configs" / "route_b_data_protocol.yaml")
    report = validate_route_b_samples(
        [row for role_rows in records.values() for row in role_rows],
        policy,
    )
    assert any(
        "semantic text template crosses internal roles" in error
        for error in report["errors"]
    )


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


def test_formal_mock_manifest_accepts_relocated_spec_paths(tmp_path: Path) -> None:
    output = tmp_path / "candidate"
    result = write_formal_mock_corpus(
        _small_spec(), output, spec_path=ROOT / "configs" / "route_b_mock_corpus_candidate_6.yaml"
    )
    manifest_path = Path(result["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["spec"]["path"] = "C:\\legacy\\IntentFence\\configs\\route_b_mock_corpus_candidate_6.yaml"
    for source in manifest["spec"]["resolved_sources"]:
        source["path"] = f"C:\\legacy\\IntentFence\\configs\\{Path(source['path']).name}"
    unsigned = deepcopy(manifest)
    unsigned.pop("sha256", None)
    serialized = json.dumps(unsigned, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    manifest["sha256"] = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

    assert validate_formal_mock_manifest(manifest_path) == []
