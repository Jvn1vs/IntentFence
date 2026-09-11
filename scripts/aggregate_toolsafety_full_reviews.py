"""Aggregate authored AI reviews without promoting them to training labels."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from verify_toolsafety_prefix_review import ALIGNMENT, RISK, digest, verify


def merge_notes(prefixes: list[dict], sources: list[tuple[str, bytes]]) -> tuple[list[dict], dict]:
    seen: set[int] = set()
    rows = []
    source_hashes = {}
    for name, payload in sources:
        if name in source_hashes:
            raise ValueError("Duplicate review source")
        source_hashes[name] = digest(payload)
        notes = json.loads(payload)
        for key, note in notes.items():
            index = int(key)
            if str(index) != key or not 0 <= index < len(prefixes) or index in seen:
                raise ValueError("Duplicate or invalid review index")
            if set(note) != {"risk", "alignment", "reason"}:
                raise ValueError("Unexpected note fields")
            if note["risk"] not in RISK | {None} or note["alignment"] not in ALIGNMENT or not isinstance(note["reason"], str) or not note["reason"].strip():
                raise ValueError("Invalid provisional judgment")
            seen.add(index)
            prefix = prefixes[index]
            rows.append({
                "index": index, "review_id": prefix["review_id"], "prefix_sha256": prefix["prefix_sha256"],
                "reviewer": "AI/Codex", "review_source": name, "review_source_sha256": digest(payload),
                "provisional_review": note, "human_verified": False, "training_ready": False,
                "risk_label": None, "alignment_label": None, "split": None,
                "review_scope": "Full pre-action context reviewed by assigned AI; not independent human verification",
            })
    rows.sort(key=lambda row: row["index"])
    result = {
        "reviewed": len(rows), "remaining": len(prefixes) - len(rows),
        "risk_counts": dict(Counter(row["provisional_review"]["risk"] or "unresolved" for row in rows)),
        "alignment_counts": dict(Counter(row["provisional_review"]["alignment"] for row in rows)),
        "source_hashes": source_hashes, "human_verified": False, "training_ready": False,
        "applied_training_labels": 0, "independent_double_review": False,
    }
    return rows, result


def aggregate(package: Path, output: Path, require_complete: bool = False) -> dict:
    if output.exists():
        raise FileExistsError("Preserve prior aggregate evidence")
    original_verification = verify(package)
    prefixes_payload = (package / "prefixes.jsonl").read_bytes()
    prefixes = [json.loads(line) for line in prefixes_payload.splitlines()]
    paths = [package / "ai_full_context_notes.json"]
    paths += sorted(package.glob("ai_full_context_batch_*_notes.json"))
    paths += sorted(package.glob("ai_full_context_agent_*_notes.json"))
    rows, result = merge_notes(prefixes, [(path.name, path.read_bytes()) for path in paths])
    if require_complete and result["remaining"]:
        raise ValueError("Full review coverage incomplete")
    # Preserve and verify earlier incremental receipts, rather than superseding them silently.
    by_id = {row["review_id"]: row for row in rows}
    for path in package.glob("ai_full_context_batch_*.jsonl"):
        for receipt in map(json.loads, path.read_bytes().splitlines()):
            current = by_id[receipt["review_id"]]
            if (receipt["prefix_sha256"] != current["prefix_sha256"]
                    or receipt["provisional_review"] != current["provisional_review"]
                    or receipt["notes_sha256"] != current["review_source_sha256"]
                    or receipt["reviewer"] != "AI/Codex" or receipt["human_verified"] is not False
                    or receipt["training_ready"] is not False):
                raise ValueError("Prior receipt changed")
    payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode("utf-8")
    result |= {"status": "ai_reviewed_quarantined" if not result["remaining"] else "ai_review_in_progress",
               "prefixes_sha256": digest(prefixes_payload), "aggregate_sha256": digest(payload),
               "implementation_sha256": digest(Path(__file__).read_bytes()),
               "supporting_review_records": {
                   path.name: digest(path.read_bytes())
                   for path in sorted(package.glob("ai_full_context_agent_*_revisions.json"))
               },
               "original_verification": original_verification,
               "limitations": ["AI judgments are provisional", "Source trajectories simulated",
                               "Upstream attribution unresolved", "Locked-set isolation not checked",
                               "No training inclusion, model training, or final-test evaluation"]}
    output.mkdir(parents=True)
    (output / "reviews.jsonl").write_bytes(payload)
    (output / "manifest.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    print(json.dumps(aggregate(args.package, args.output, args.require_complete), indent=2))
