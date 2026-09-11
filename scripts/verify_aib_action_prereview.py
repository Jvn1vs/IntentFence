"""Read-only validation of single nonblind AI opinions; never applies labels."""

import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "data/interim/aib_action_prereview_20260911/review.json"
EXPECTED = "2dd51ba115516c1c9e7589478147cef9242e5cabae31809ee7cc6f55fdc16a3a"


def verify(payload: dict, root: Path) -> dict:
    expected_actions = {}
    receipts = {}
    for receipt in payload["input_receipts"]:
        relative = receipt["path"]
        path = (root / relative).resolve()
        if root.resolve() not in path.parents:
            raise ValueError("input outside workspace")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != receipt["sha256"] or relative in receipts:
            raise ValueError("input hash mismatch or duplicate receipt")
        receipts[relative] = receipt["sha256"]
        rows = [json.loads(data)] if path.name == "record.json" else [
            json.loads(line) for line in data.splitlines()]
        for row in rows:
            cid = row.get("case_id") or row.get("source_id") or row.get("source_binding", {}).get("case_id")
            for i, observation in enumerate(row.get("observations") or [row["observation"]]):
                key = f"{cid}:{i}"
                if key in expected_actions:
                    raise ValueError("duplicate action identity")
                action_sha = hashlib.sha256(json.dumps(observation["candidate_action"],
                    sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
                expected_actions[key] = (relative, receipt["sha256"], action_sha)
    seen = set()
    for review in payload["reviews"]:
        key = review["key"]
        if key in seen or key not in expected_actions:
            raise ValueError("duplicate or unknown review")
        seen.add(key)
        if (review["source_file"], review["source_file_sha256"], review["action_sha256"]) != expected_actions[key]:
            raise ValueError("review binding mismatch")
        if any(review[field] is not False for field in [
            "blind", "independent_of_preparation", "human_verified", "applied_to_training"
        ]) or review["reviewer"] != "Codex/AI":
            raise ValueError("evidence identity misrepresented")
        label = review["alignment_opinion"]
        if label not in {None, "aligned", "unrelated", "ambiguous", "malicious"}:
            raise ValueError("unknown alignment")
        expected_status = "unable_to_determine" if label is None else "completed"
        if review["review_status"] != expected_status or not review["reason"].strip():
            raise ValueError("invalid abstention or missing rationale")
        if review["action_realism_opinion"] not in {"realistic", "unrealistic", "ambiguous"}:
            raise ValueError("invalid realism opinion")
    if seen != set(expected_actions):
        raise ValueError("review coverage incomplete")
    if payload["human_verified"] is not False or payload["training_ready"] is not False:
        raise ValueError("unsupported evidence promotion")
    return {"reviews": len(seen), "alignment_opinions": dict(Counter(
        r["alignment_opinion"] or "abstain" for r in payload["reviews"])),
        "realism_opinions": dict(Counter(r["action_realism_opinion"] for r in payload["reviews"]))}


if __name__ == "__main__":
    data = REVIEW.read_bytes()
    if hashlib.sha256(data).hexdigest() != EXPECTED:
        raise ValueError("review snapshot changed")
    print(json.dumps(verify(json.loads(data), ROOT), ensure_ascii=False, indent=2))
