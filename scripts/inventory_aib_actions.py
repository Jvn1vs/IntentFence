"""Inventory pinned pilot evidence without merging it into a training dataset."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = [
    ("aib_action_pilot_20260911", "observations.jsonl",
     "9476c6935f7b58bcee77fd4e45dc7b1ef4b2f25037d46387c01a5f0c9eac66ee"),
    ("aib_communication_pilot_20260911", "records.jsonl",
     "40b09e46e31c64982e8515fbe643e8752efb17f314507190e5e99275c3214fee"),
    ("aib_risk_pilot_20260911", "records.jsonl",
     "d84b4f3e7e81b2794fa69d51b993211e18249febc2799718c93a191b76f7bf40"),
]
REVIEW_SHA = "259689b354db7405e8aa63740f717db0f94b5b5d71502858e8886f476f08982a"


def sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def inspect_record(record: dict) -> tuple[str, list[dict]]:
    case_id = record.get("case_id") or record["source_binding"]["case_id"]
    for key in ["risk_label", "task_alignment_label", "task_alignment_labels", "split"]:
        if record.get(key) is not None:
            raise ValueError("unexpected applied labels or split")
    if record["human_verified"] is not False or record["training_ready"] is not False:
        raise ValueError("unexpected evidence promotion")
    observations = record.get("observations")
    if observations is None:
        observations = [record["observation"]]
    if not observations:
        raise ValueError("empty observation set")
    for observation in observations:
        if observation["executed"] is not False or observation["external_side_effects"] is not False:
            raise ValueError("unexpected tool execution")
    return case_id, observations


def main() -> None:
    review_bytes = (ROOT / "data/interim/aib_scenarios_20260911/aggregate/reviews.jsonl").read_bytes()
    if sha(review_bytes) != REVIEW_SHA:
        raise ValueError("scenario review snapshot changed")
    reviews = {r["source_id"]: r["provisional_scenario_review"]
               for r in map(json.loads, review_bytes.splitlines())}
    inventory = []
    seen = set()
    receipts = []
    for name, records_name, expected_manifest in RUNS:
        folder = ROOT / "data/interim" / name / "run_v1"
        manifest_bytes = (folder / "manifest.json").read_bytes()
        if sha(manifest_bytes) != expected_manifest:
            raise ValueError(f"manifest changed: {name}")
        manifest = json.loads(manifest_bytes)
        records_bytes = (folder / records_name).read_bytes()
        if sha(records_bytes) != manifest["records_sha256"]:
            raise ValueError(f"records changed: {name}")
        receipts.append({"run": name, "manifest_sha256": expected_manifest,
                         "records_sha256": sha(records_bytes)})
        for record in map(json.loads, records_bytes.splitlines()):
            case_id, observations = inspect_record(record)
            if case_id in seen:
                raise ValueError("duplicate source case across runs requires explicit reconciliation")
            seen.add(case_id)
            proposals = [o for o in observations if o["candidate_action"]["tool"] != "memory.clarification"]
            distinct = {json.dumps(o["candidate_action"], sort_keys=True) for o in proposals}
            prefix_hashes = {o["prefix_sha256"] for o in proposals if "prefix_sha256" in o}
            if len(prefix_hashes) > 1:
                raise ValueError("contrast prefix mismatch")
            inventory.append({
                "source_id": case_id, "run": name,
                "provisional_scenario_risk": reviews[case_id]["risk"],
                "unreconciled_family_name": reviews[case_id]["family"],
                "observations": len(observations), "proposals": len(proposals),
                "clarifications": len(observations) - len(proposals),
                "distinct_action_contrast": len(distinct) >= 2 and len(prefix_hashes) == 1,
                "tools": [o["candidate_action"]["tool"] for o in observations],
                "risk_label": None, "alignment_labels": None, "split": None,
                "human_verified": False, "training_ready": False,
            })
    summary = {
        "source_receipts": receipts, "scenario_review_sha256": REVIEW_SHA,
        "cases": len(inventory), "proposals": sum(r["proposals"] for r in inventory),
        "clarifications": sum(r["clarifications"] for r in inventory),
        "case_risk_provisional_counts": dict(Counter(r["provisional_scenario_risk"] for r in inventory)),
        "contrast_case_risk_provisional_counts": dict(Counter(
            r["provisional_scenario_risk"] for r in inventory if r["distinct_action_contrast"])),
        "independent_alignment_review_complete": False, "family_isolation_complete": False,
        "training_ready": False, "human_verified": False,
    }
    folder = ROOT / "data/interim/aib_action_inventory_20260911"
    folder.mkdir(exist_ok=False)
    for name, value in [("inventory.json", inventory), ("summary.json", summary)]:
        with (folder / name).open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
