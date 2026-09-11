"""Join frozen preparation evidence; never assign labels or dataset splits."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from scripts.verify_aib_action_prereview import EXPECTED, verify

ROOT = Path(__file__).resolve().parents[1]


def assemble(reviews: list[dict], scenarios: dict, components: list[list[str]]) -> dict:
    membership = {}
    for group in components:
        if not group:
            raise ValueError("empty constraint group")
        for case in group:
            if case in membership:
                raise ValueError("duplicate constraint membership")
            membership[case] = sorted(group)
    entries, seen = [], set()
    for review in reviews:
        key = review["key"]
        if key in seen:
            raise ValueError("duplicate review")
        seen.add(key)
        case = key.rsplit(":", 1)[0]
        if case not in scenarios or case not in membership:
            raise ValueError("missing scenario or constraint membership")
        gaps = ["independent_review_missing", "family_isolation_incomplete",
                "split_not_constructed", "not_training_authorized"]
        if review["alignment_opinion"] is None:
            gaps.append("alignment_abstention")
        if review["action_realism_opinion"] != "realistic":
            gaps.append("action_realism_" + review["action_realism_opinion"])
        entries.append({
            "key": key, "source_id": case, "source_file": review["source_file"],
            "action_sha256": review["action_sha256"],
            "provisional_scenario_risk": scenarios[case]["risk"],
            "alignment_opinion": review["alignment_opinion"],
            "realism_opinion": review["action_realism_opinion"],
            "constraint_group_members": membership[case], "remaining_gaps": gaps,
            "risk_label": None, "alignment_label": None, "split": None,
            "human_verified": False, "training_ready": False,
        })
    cases = sorted({r["source_id"] for r in entries})
    pairs = []
    for case in cases:
        eligible = [r for r in entries if r["source_id"] == case
                    and r["realism_opinion"] == "realistic" and r["alignment_opinion"] is not None]
        if len({r["alignment_opinion"] for r in eligible}) >= 2:
            pairs.append(case)
    return {"entries": entries, "summary": {
        "cases": len(cases), "observations": len(entries),
        "case_risk_opinions": dict(Counter(scenarios[c]["risk"] for c in cases)),
        "alignment_opinions": dict(Counter(r["alignment_opinion"] or "abstain" for r in entries)),
        "realism_opinions": dict(Counter(r["realism_opinion"] for r in entries)),
        "cases_with_different_nonabstained_realistic_opinions": pairs,
        "pair_scope": "Opinion coverage only, not independent labels or same-prefix validation.",
        "training_ready": False, "labels_applied": 0,
    }}


def main() -> None:
    receipts = {}

    def read(rel: str, expected: str) -> bytes:
        data = (ROOT / rel).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != expected:
            raise ValueError(f"Changed input: {rel}")
        receipts[rel] = digest
        return data

    reviews = json.loads(read("data/interim/aib_action_prereview_20260911/review.json", EXPECTED))
    verify(reviews, ROOT)
    scenarios = {r["source_id"]: r["provisional_scenario_review"] for r in map(json.loads, read(
        "data/interim/aib_scenarios_20260911/aggregate/reviews.jsonl",
        "259689b354db7405e8aa63740f717db0f94b5b5d71502858e8886f476f08982a").splitlines())}
    constraints = json.loads(read("data/interim/aib_family_constraints_20260911/constraints.json",
        "635bdebe9cc1e1f15e41c455123eb999d17673cbce3b0156b75fef5e38b65d2f"))
    result = assemble(reviews["reviews"], scenarios, constraints["components"])
    result["input_receipts"] = receipts
    result["action_file_receipts"] = reviews["input_receipts"]
    result["review_provenance"] = "Single nonblind Codex/AI, not independent of preparation"
    result["implementation_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    path = ROOT / "data/interim/aib_preparation_register_20260911/register.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result["summary"], indent=2))
    print("sha256", hashlib.sha256(path.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
