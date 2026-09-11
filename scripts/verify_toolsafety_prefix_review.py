"""Replay isolated prefixes and validate AI sidecars without executing source tools."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RISK = {"benign", "instruction_hijacking", "data_exfiltration", "privilege_escalation", "tool_manipulation"}
ALIGNMENT = {"aligned", "unrelated", "ambiguous", "malicious"}


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def validate_prefix(prefix: dict, source: dict) -> None:
    """Check exact source boundary, including absence of any later turns."""
    index = prefix["tool_turn_index_zero_based"]
    turns = source["conversations"]
    if not 1 <= index < len(turns) - 1:
        raise ValueError("Invalid tool boundary")
    history, action = turns[:index + 1], turns[index + 1]["value"]
    expected_hash = digest(json.dumps([source["system"], history, action], ensure_ascii=False, sort_keys=True).encode())
    expected = {
        "system_and_tool_definitions": source["system"], "history_before_action": history,
        "user_goal": turns[0]["value"], "untrusted_content": turns[index]["value"],
        "proposed_action": action, "prefix_sha256": expected_hash,
        "review_id": f"ts-{prefix['record_index_zero_based']}-{index}-{expected_hash[:12]}",
        "risk_review": None, "alignment_review": None, "reviewer": None,
        "human_verified": False, "training_ready": False, "split": None,
        "source_revision": "7c444473e0dc0a822247858c249b10856ade04ef",
        "source_license_declared": "MIT", "upstream_attribution_status": "unresolved",
        "locked_set_isolation_status": "not_checked", "action_provenance": "source_field",
        "source_execution_reality": "simulated_trajectory_not_real_execution_proof",
    }
    if turns[index]["from"] != "tool" or turns[index + 1]["from"] != "assistant":
        raise ValueError("Not a tool/action boundary")
    if set(prefix) != set(expected) | {"record_index_zero_based", "tool_turn_index_zero_based"}:
        raise ValueError("Unexpected prefix fields")
    for key, value in expected.items():
        if prefix[key] != value:
            raise ValueError(f"Source replay mismatch: {key}")


def validate_reviews(prefixes: list[dict], reviews: list[dict]) -> dict:
    by_id = {p["review_id"]: p for p in prefixes}
    ids = [r["review_id"] for r in reviews]
    if len(by_id) != len(prefixes) or len(set(ids)) != len(ids) or set(ids) != set(by_id):
        raise ValueError("Missing, duplicate, or foreign review")
    full_count = 0
    for review in reviews:
        if review["prefix_sha256"] != by_id[review["review_id"]]["prefix_sha256"]:
            raise ValueError("Review hash mismatch")
        if review["reviewer"] != "AI/Codex" or review["human_verified"] is not False or review["training_ready"] is not False:
            raise ValueError("Invalid AI provenance or readiness")
        if not review["semantic_note"].strip() or review["risk_label"] is not None or review["alignment_label"] is not None:
            raise ValueError("Missing semantic note or applied training label")
        full = review["full_context_pre_review"]
        if full is not None:
            if full["risk"] not in RISK or full["alignment"] not in ALIGNMENT or not full["reason"].strip():
                raise ValueError("Invalid independent provisional labels")
            full_count += 1
    return {"ai_focused_pre_review_rows": len(reviews), "ai_full_context_pre_review_rows": full_count,
            "applied_training_labels": 0, "human_verified": False, "training_ready": False}


def verify(package: Path) -> dict:
    manifest = json.loads((package / "manifest.json").read_bytes())
    approval_bytes = (ROOT / "configs/toolsafety_prefix_review_20260911.yaml").read_bytes()
    config = yaml.safe_load(approval_bytes)
    raw = (ROOT / "data/raw/toolsafety/toolsafety.json").read_bytes()
    diagnostics = (ROOT / "data/interim/toolsafety_audit_20260910/diagnostics.json").read_bytes()
    payload = (package / "prefixes.jsonl").read_bytes()
    for key, value in {"source_sha256": raw, "diagnostics_sha256": diagnostics, "approval_sha256": approval_bytes,
                       "prefixes_sha256": payload, "implementation_sha256": (ROOT / "scripts/build_toolsafety_prefix_review.py").read_bytes()}.items():
        if digest(value) != manifest[key]:
            raise ValueError(f"Manifest hash mismatch: {key}")
    if config["owner_approved"] is not True or not 1 <= config["max_records"] <= 200:
        raise ValueError("Approval missing")
    if digest(raw) != config["source_sha256"] or digest(diagnostics) != config["diagnostics_sha256"]:
        raise ValueError("Approved input mismatch")
    source = json.loads(raw)
    by_record = defaultdict(list)
    for item in json.loads(diagnostics)["position_evidence"]:
        if item["definition_status"] == "unique_definitions" and not item["findings"]:
            by_record[item["record_index_zero_based"]].append(item["tool_turn_index_zero_based"])
    rng = random.Random(config["seed"])
    expected_records = rng.sample(sorted(by_record), min(config["max_records"], len(by_record)))
    expected_pairs = [(i, rng.choice(sorted(by_record[i]))) for i in expected_records]
    prefixes = [json.loads(line) for line in payload.splitlines()]
    if [(p["record_index_zero_based"], p["tool_turn_index_zero_based"]) for p in prefixes] != expected_pairs:
        raise ValueError("Sampling replay mismatch")
    if manifest["rows"] != len(prefixes) or manifest["eligible_conversations"] != len(by_record):
        raise ValueError("Manifest count mismatch")
    for prefix in prefixes:
        validate_prefix(prefix, source[prefix["record_index_zero_based"]])
    reviews_bytes = (package / "ai_pre_reviews.jsonl").read_bytes()
    reviews = [json.loads(line) for line in reviews_bytes.splitlines()]
    result = validate_reviews(prefixes, reviews)
    notes_bytes = (package / "ai_notes.json").read_bytes()
    full_bytes = (package / "ai_full_context_notes.json").read_bytes()
    notes, full = json.loads(notes_bytes), json.loads(full_bytes)
    if set(notes) != {str(i) for i in range(len(prefixes))} or not set(full) <= set(notes):
        raise ValueError("Authored note coverage mismatch")
    review_by_id = {row["review_id"]: row for row in reviews}
    for i, prefix in enumerate(prefixes):
        row = review_by_id[prefix["review_id"]]
        if (row["ai_notes_sha256"] != digest(notes_bytes) or row["ai_full_context_notes_sha256"] != digest(full_bytes)
                or row["semantic_note"] != notes[str(i)] or row["full_context_pre_review"] != full.get(str(i))):
            raise ValueError("Authored note binding mismatch")
        if row["independent_human_review"] is not False or row["labels_applied_to_training"] is not False:
            raise ValueError("Review scope expanded")
    return result | {"status": "integrity_verified_quarantined", "prefixes_sha256": digest(payload),
                     "reviews_sha256": digest(reviews_bytes), "verifier_sha256": digest(Path(__file__).read_bytes()),
                     "source_rows_replayed": len(prefixes), "final_test_clearance": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.package), indent=2))
