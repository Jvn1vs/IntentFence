"""Bind human-readable AI scenario notes to source rows without applying labels."""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
FIELDS = {"risk", "carrier", "family", "goal", "boundary", "action_gap", "reason"}
RISKS = {"benign", "instruction_hijacking", "data_exfiltration", "privilege_escalation", "tool_manipulation"}


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def strict_object(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def aggregate(rows: list[dict], sources: dict[str, bytes], partitions: dict[str, list[int]]) -> tuple[list[dict], dict]:
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError("Duplicate source ID")
    if set(sources) != set(partitions):
        raise ValueError("Missing or unexpected review partition")
    by_id = {row["id"]: row for row in rows}
    seen = set()
    output = []
    for reviewer, payload in sorted(sources.items()):
        notes = json.loads(payload, object_pairs_hook=strict_object)
        lo, hi = partitions[reviewer]
        expected = {row["id"] for row in rows[lo:hi+1]}
        if set(notes) != expected or seen.intersection(notes):
            raise ValueError("Partition mismatch or overlapping reviewers")
        for case_id, note in notes.items():
            if set(note) != FIELDS or note["risk"] not in RISKS | {None}:
                raise ValueError("Invalid note fields or risk")
            if any(not isinstance(note[key], str) or not note[key].strip() for key in FIELDS - {"risk"}):
                raise ValueError("Missing semantic evidence")
            if not re.fullmatch(r"[a-z][a-z0-9_]*", note["family"]):
                raise ValueError("Invalid provisional family")
            output.append({
                "source_id": case_id,
                "source_row_sha256": digest(json.dumps(by_id[case_id], sort_keys=True, ensure_ascii=False).encode()),
                "reviewer": "AI/Codex", "partition": reviewer, "review_file_sha256": digest(payload),
                "provisional_scenario_review": note,
                "risk_label": None, "task_alignment_label": None, "proposed_action": None,
                "human_verified": False, "training_ready": False, "split": None,
            })
        seen.update(notes)
    if seen != set(by_id):
        raise ValueError("Incomplete full review")
    output.sort(key=lambda row: row["source_id"])
    return output, {
        "reviewed": len(output),
        "provisional_risk_counts": dict(Counter(row["provisional_scenario_review"]["risk"] or "unresolved" for row in output)),
        "provisional_family_counts": dict(Counter(row["provisional_scenario_review"]["family"] for row in output)),
        "independent_double_review": False, "human_verified": False, "training_ready": False,
        "family_isolation_cleared": False, "applied_training_labels": 0,
    }


def main() -> None:
    cfg_path = ROOT / "configs/aib_scenario_review_20260911.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    if cfg["owner_approved"] is not True:
        raise ValueError("Review not approved")
    payload = (ROOT / "data/raw/agent_injection_bench/data/agent_injection_bench.jsonl").read_bytes()
    if digest(payload) != cfg["source_sha256"]:
        raise ValueError("Source changed")
    rows = [json.loads(line, object_pairs_hook=strict_object) for line in payload.splitlines()]
    if len(rows) != cfg["expected_rows"]:
        raise ValueError("Unexpected source count")
    folder = ROOT / "data/interim/aib_scenarios_20260911"
    sources = {name: (folder / f"{name}.json").read_bytes() for name in cfg["review_partition_zero_based_inclusive"]}
    reviews, report = aggregate(rows, sources, cfg["review_partition_zero_based_inclusive"])
    output = folder / "aggregate"
    if output.exists():
        raise FileExistsError("Preserve earlier review aggregate")
    result = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in reviews).encode()
    report |= {"source_sha256": digest(payload), "revision": cfg["source_revision"],
               "config_sha256": digest(cfg_path.read_bytes()), "implementation_sha256": digest(Path(__file__).read_bytes()),
               "review_sources": {name: digest(value) for name, value in sources.items()},
               "reviews_sha256": digest(result), "status": "ai_scenario_inventory_quarantined"}
    output.mkdir()
    (output / "reviews.jsonl").write_bytes(result)
    (output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
