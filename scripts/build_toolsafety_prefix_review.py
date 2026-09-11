"""Build owner-approved quarantined prefixes, excluding all future outcomes."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def make_prefix(row: dict, record_index: int, tool_index: int) -> dict:
    turns = row["conversations"]
    if turns[0]["from"] != "user" or turns[tool_index]["from"] != "tool" or turns[tool_index + 1]["from"] != "assistant":
        raise ValueError("Unexpected prefix boundary")
    history = turns[:tool_index + 1]
    action = turns[tool_index + 1]["value"]
    prefix_hash = sha(json.dumps([row["system"], history, action], ensure_ascii=False, sort_keys=True).encode())
    return {
        "review_id": f"ts-{record_index}-{tool_index}-{prefix_hash[:12]}",
        "record_index_zero_based": record_index, "tool_turn_index_zero_based": tool_index,
        "source_revision": "7c444473e0dc0a822247858c249b10856ade04ef",
        "source_license_declared": "MIT", "system_and_tool_definitions": row["system"],
        "user_goal": turns[0]["value"], "history_before_action": history,
        "untrusted_content": turns[tool_index]["value"], "proposed_action": action,
        "prefix_sha256": prefix_hash,
        "risk_review": None, "alignment_review": None, "reviewer": None,
        "human_verified": False, "training_ready": False, "split": None,
        "upstream_attribution_status": "unresolved", "locked_set_isolation_status": "not_checked",
        "action_provenance": "source_field", "source_execution_reality": "simulated_trajectory_not_real_execution_proof",
    }


def build(output: Path) -> None:
    approval_bytes = (ROOT / "configs/toolsafety_prefix_review_20260911.yaml").read_bytes()
    config = yaml.safe_load(approval_bytes)
    if config["owner_approved"] is not True or not 1 <= config["max_records"] <= 200:
        raise ValueError("Missing approval or invalid approved size")
    if output.exists():
        raise FileExistsError("Refusing to overwrite review package")
    raw = (ROOT / "data/raw/toolsafety/toolsafety.json").read_bytes()
    diagnostics = (ROOT / "data/interim/toolsafety_audit_20260910/diagnostics.json").read_bytes()
    if sha(raw) != config["source_sha256"] or sha(diagnostics) != config["diagnostics_sha256"]:
        raise ValueError("Pinned input changed")
    rows = json.loads(raw)
    by_record = defaultdict(list)
    for item in json.loads(diagnostics)["position_evidence"]:
        if not item["findings"] and item["definition_status"] == "unique_definitions":
            by_record[item["record_index_zero_based"]].append(item["tool_turn_index_zero_based"])
    rng = random.Random(config["seed"])
    record_ids = rng.sample(sorted(by_record), min(config["max_records"], len(by_record)))
    selected = [make_prefix(rows[i], i, rng.choice(sorted(by_record[i]))) for i in record_ids]
    output.mkdir(parents=True)
    payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in selected).encode("utf-8")
    (output / "prefixes.jsonl").write_bytes(payload)
    manifest = {
        "status": "quarantined_pending_ai_pre_review", "rows": len(selected), "seed": config["seed"],
        "sampling": "Uniform sample of eligible unique-definition conversations, then one uniformly selected eligible position per sampled conversation; no stratification or population coverage claim.",
        "eligible_conversations": len(by_record), "source_sha256": sha(raw),
        "diagnostics_sha256": sha(diagnostics), "approval_sha256": sha(approval_bytes),
        "implementation_sha256": sha(Path(__file__).read_bytes()), "prefixes_sha256": sha(payload),
        "training_ready": False, "human_verified": False,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    build(parser.parse_args().output)
