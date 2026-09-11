"""Render two pinned pilot actions for inspection without changing their reviews."""
import hashlib
import json
from pathlib import Path

from intentfence.action_review_views import bucket_request_view, missing_email_body_view

ROOT = Path(__file__).resolve().parents[1]


def main():
    entries = []
    for rel, expected, case, index, renderer in [
        ("data/interim/aib_risk_pilot_20260911/run_v1/records.jsonl",
         "0d71472188edcd004c1c732ed9da36b84dd4705171b43ff216b9a199712b99f5",
         "AIB-00032", 1, bucket_request_view),
        ("data/interim/aib_communication_pilot_20260911/run_v1/records.jsonl",
         "cb963ae88b20e3810e9e9543303a8c23532d7396da546760c282aa24b20a561b",
         "AIB-00159", 0, missing_email_body_view),
    ]:
        data = (ROOT / rel).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("source action file changed")
        matches = [r for r in map(json.loads, data.splitlines()) if r["source_binding"]["case_id"] == case]
        if len(matches) != 1:
            raise ValueError("nonunique case")
        row = matches[0]
        observation = (row.get("observations") or [row["observation"]])[index]
        candidate = observation["candidate_action"]
        entries.append({"key": f"{case}:{index}", "source_file": rel, "source_sha256": expected,
                        "original_candidate": candidate, "review_view": renderer(candidate),
                        "new_training_sample": False, "label_applied": False})
    result = {"entries": entries, "training_ready": False, "independent_review": False,
              "implementation_hashes": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in [Path(__file__), ROOT / "src/intentfence/action_review_views.py"]}}
    out = ROOT / "data/interim/aib_action_review_views_20260911/views.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print("views", len(entries), "sha256", hashlib.sha256(out.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
