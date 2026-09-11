"""Read-only text screening of three reviewed source prefixes, not clearance."""
from __future__ import annotations

import hashlib
import json
from contextlib import suppress
from pathlib import Path

from intentfence.candidate9 import SimilarityIndex

ROOT = Path(__file__).resolve().parents[1]


def string_leaves(value: object) -> list[str]:
    """Include nested textual values, without evaluating source expressions."""
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [s for item in value for s in string_leaves(item)]
    if isinstance(value, dict):
        return [s for item in value.values() for s in string_leaves(item)]
    return []


def prefix_texts(row: dict) -> list[str]:
    found = [row["user_goal"]]
    for message in row["history_before_action"]:
        if message["from"] not in {"user", "tool"}:
            continue
        value = message["value"]
        found.append(value)
        if message["from"] == "tool":
            with suppress(json.JSONDecodeError):
                found.extend(string_leaves(json.loads(value)))
    return sorted(set(found))


def main() -> None:
    hashes = {}

    def read(rel: str, expected: str | None = None) -> bytes:
        data = (ROOT / rel).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if expected is not None and digest != expected:
            raise ValueError(f"Changed input: {rel}")
        hashes[rel] = digest
        return data

    review = json.loads(read(
        "data/interim/toolsafety_targeted_rereview_20260911/review.json",
        "b073e0f7a987c7b0d2e658fdef7b8789dbb11585a8c834fe715bfaaccfd39777",
    ))
    rows = [json.loads(line) for line in read(
        "data/interim/toolsafety_prefix_review_20260911/prefixes.jsonl",
        "bb978876abb0ced7c2c8dafd51c6fc1902eb542a2296a25ada07fd4410e3121f",
    ).splitlines()]
    ids = {r["review_id"] for r in review["entries"]}
    selected = [r for r in rows if r["review_id"] in ids]
    if len(selected) != 3 or len({r["review_id"] for r in selected}) != 3:
        raise ValueError("Expected three unique reviewed prefixes")
    receipt = json.loads(read("data/interim/aib_audit_20260911/audit_v2.json"))
    locked_hashes = receipt["locked_text_screen"]["input_hashes"]
    protected = []
    for rel, digest in locked_hashes.items():
        data = read(rel, digest)
        if rel.replace("\\", "/").endswith("text_attack_test.json"):
            protected.extend(t for values in json.loads(data).values() for t in values)
        else:
            for line in data.splitlines():
                row = json.loads(line)
                protected.extend(row[k] for k in ("user_goal", "untrusted_content", "context")
                                 if isinstance(row.get(k), str))
    index = SimilarityIndex(protected, 5, 0.8)
    findings = []
    for row in selected:
        queries = prefix_texts(row)
        findings.append({"review_id": row["review_id"], "query_count": len(queries),
                         "matched_query_count": sum(bool(index.matches(q)) for q in queries)})
    report = {"input_hashes": hashes, "protected_files": len(locked_hashes),
              "protected_texts": len(protected), "width": 5, "jaccard": 0.8,
              "findings": findings, "complete_source_clearance": False,
              "training_ready": False, "labels_applied": 0,
              "limitations": "Only user/tool pre-action text and JSON string leaves. No semantic, "
              "tool-family or complete AgentDojo clearance. No test outcomes read.",
              "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    out = ROOT / "data/interim/toolsafety_targeted_screen_20260911/screen_v2.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "input_hashes"}, indent=2))
    print("report_sha256", hashlib.sha256(out.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
