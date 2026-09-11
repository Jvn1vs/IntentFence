"""Read-only structural and text-overlap audit; never execute source actions."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import yaml

from intentfence.candidate9 import SimilarityIndex, norm

ROOT = Path(__file__).resolve().parents[1]


def texts(row: dict, role: str) -> list[str]:
    return [m["content"] for m in row["conversation"] if m["role"] == role]


def summarize(rows: list[dict]) -> dict:
    ids = [r["id"] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate case IDs")
    counters = {k: dict(Counter(r[k] for r in rows)) for k in
                ("attack_category", "attacker_intent", "ground_truth", "complexity")}
    actions = [{"id": r["id"], "turn": i, "after_tool_result": i > 0 and r["conversation"][i-1]["role"] == "tool_result"}
               for r in rows for i, m in enumerate(r["conversation"])
               if m["role"] == "tool_call" or m.get("tool_calls")]
    role_counts = Counter(m["role"] for r in rows for m in r["conversation"])
    duplicate_groups = {}
    for role in ("user", "tool_result"):
        groups: dict[str, set[str]] = {}
        for r in rows:
            for text in texts(r, role):
                groups.setdefault(norm(text), set()).add(r["id"])
        duplicate_groups[role] = sorted(sorted(g) for g in groups.values() if len(g) > 1)
    return {"rows": len(rows), "counts": counters, "role_counts": dict(role_counts),
            "explicit_action_fields": actions, "exact_shared_text_groups": duplicate_groups,
            "training_ready": False, "human_verified": False, "labels_applied": 0}


def main() -> None:
    raw = ROOT / "data/raw/agent_injection_bench"
    config_path = ROOT / "configs/candidate_9_aib_audit_proposal_20260911.yaml"
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if cfg["owner_approved"] is not True:
        raise ValueError("Source audit not approved")
    hashes = {}
    for f in cfg["files"]:
        b = (raw / f["path"]).read_bytes()
        if len(b) != f["bytes"] or hashlib.sha1(b"blob " + str(len(b)).encode() + b"\0" + b).hexdigest() != f["git_blob_oid"]:
            raise ValueError("Pinned source changed")
        hashes[f["path"]] = hashlib.sha256(b).hexdigest()
    rows = [json.loads(line) for line in (raw / "data/agent_injection_bench.jsonl").read_text(encoding="utf-8").splitlines()]
    report = summarize(rows)
    queries = [(r["id"], role, t) for r in rows for role in ("user", "tool_result") for t in texts(r, role)]
    local = SimilarityIndex([t for _, _, t in queries], 5, 0.8)
    report["near_duplicate_pairs"] = [
        [queries[i][0], role, queries[j][0], queries[j][1]]
        for i, (_, role, t) in enumerate(queries) for j in local.matches(t)
        if j < i and queries[j][0] != queries[i][0]
    ]
    base = yaml.safe_load((ROOT / "configs/candidate_9.yaml").read_text(encoding="utf-8"))
    extra = yaml.safe_load((ROOT / "configs/candidate_9_v3.yaml").read_text(encoding="utf-8"))
    paths = base["locked_inputs"] + extra["additional_locked_inputs"]
    paths += ["data/interim/candidate_9_v3/calibration.jsonl", "data/interim/candidate_9_v3/test_a.jsonl"]
    paths += [f"data/raw/bipia/benchmark/{task}/test.jsonl" for task in base["tasks"]]
    protected, missing, locked_hashes = [], [], {}
    for rel in paths:
        p = ROOT / rel
        if not p.exists():
            missing.append(rel)
            continue
        b = p.read_bytes()
        locked_hashes[rel] = hashlib.sha256(b).hexdigest()
        for line in b.splitlines():
            row = json.loads(line)
            protected.extend(row[k] for k in ("user_goal", "untrusted_content", "context") if isinstance(row.get(k), str))
    attack_path = ROOT / "data/raw/bipia/benchmark/text_attack_test.json"
    b = attack_path.read_bytes()
    locked_hashes[str(attack_path.relative_to(ROOT))] = hashlib.sha256(b).hexdigest()
    protected.extend(t for values in json.loads(b).values() for t in values)
    locked = SimilarityIndex(protected, 5, 0.8)
    report["locked_text_screen"] = {
        "protected_texts": len(protected), "missing_paths": missing,
        "matched_case_ids": sorted({case for case, _, t in queries if locked.matches(t)}),
        "input_hashes": locked_hashes, "width": 5, "jaccard": 0.8,
        "complete_source_clearance": False,
        "limitations": "Text screening only; no semantic/template/tool-family or complete AgentDojo clearance. No test outcomes accessed.",
    }
    report |= {"source_hashes": hashes, "revision": cfg["revision"],
               "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "approval_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest()}
    out = ROOT / "data/interim/aib_audit_20260911"
    out.mkdir(parents=True, exist_ok=True)
    target = out / "audit_v2.json"
    if target.exists():
        raise FileExistsError("Preserve prior audit")
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("near_duplicate_pairs", "locked_text_screen")}, indent=2))
    print("Near duplicate pairs:", len(report["near_duplicate_pairs"]))
    print("Protected matches:", report["locked_text_screen"]["matched_case_ids"], "missing:", missing)


if __name__ == "__main__":
    main()
