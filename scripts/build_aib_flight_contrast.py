"""Build/replay the pinned AIB-00175 contrast, without applying labels."""
import argparse
import hashlib
import json
from pathlib import Path

from intentfence.flight_contrast import contrast
from intentfence.offline_actions import Message

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = "606cb74f5ce874dba45d9cdf591af678d7c6bd8a92ff3189d0f522fb39fb941e"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    blob = (ROOT / "data/raw/agent_injection_bench/data/agent_injection_bench.jsonl").read_bytes()
    if hashlib.sha256(blob).hexdigest() != SOURCE_SHA:
        raise ValueError("changed source")
    rows = [line for line in blob.splitlines() if json.loads(line)["id"] == "AIB-00175"]
    if len(rows) != 1:
        raise ValueError("missing or duplicate case")
    row = json.loads(rows[0])
    prefix = [Message(role="system", content=row["system_prompt"])] + [
        Message(role=m["role"], content=m["content"]) for m in row["conversation"][:2]]
    note = json.loads(prefix[-1].content)["sponsored_note"]
    carrier = "BlueSky"
    if note.count(carrier) != 1:
        raise ValueError("ambiguous prepared carrier")
    start = note.index(carrier)
    observations = contrast(prefix, carrier, start, start + len(carrier))
    constraint_path = ROOT / "data/interim/aib_family_constraints_20260911/constraints.json"
    constraint_bytes = constraint_path.read_bytes()
    if hashlib.sha256(constraint_bytes).hexdigest() != "635bdebe9cc1e1f15e41c455123eb999d17673cbce3b0156b75fef5e38b65d2f":
        raise ValueError("changed family receipt")
    groups = [g for g in json.loads(constraint_bytes)["components"] if row["id"] in g]
    if len(groups) != 1:
        raise ValueError("missing family membership")
    result = {"source_id": row["id"], "source_sha256": SOURCE_SHA,
        "source_revision": "ef230359966c4d87b1c925aa56b8bf6e3f6ffed3",
        "row_sha256": hashlib.sha256(rows[0]).hexdigest(), "conversation_boundary": 2,
        "prefix": [m.model_dump() for m in prefix], "observations": observations,
        "preparation_author": "Codex/AI", "prepared_promoted_carrier": carrier,
        "preparation_reason": "Source note explicitly requests promoting the higher priced option and omitting its competitor.",
        "constraint_group_members": groups[0], "family_isolation_complete": False,
        "limitations": ["No currency, date or route is supplied in results; claims restricted to returned options.",
                        "Counterfactual is engineered, not an observed model failure."],
        "risk_label": None, "alignment_labels": None, "split": None,
        "human_verified": False, "training_ready": False,
        "implementation_hashes": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [Path(__file__), ROOT / "src/intentfence/flight_contrast.py"]}}
    out = ROOT / "data/interim/aib_flight_contrast_20260911/record.json"
    if args.verify:
        if json.loads(out.read_text(encoding="utf-8")) != result:
            raise ValueError("replay mismatch")
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(result, indent=2) + "\n")
    print("actions", len(observations), "sha256", hashlib.sha256(out.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
