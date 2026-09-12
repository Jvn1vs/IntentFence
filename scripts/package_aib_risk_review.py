"""Package current low-trust content for Risk review, excluding action opinions."""
import csv
import hashlib
import io
import json
from pathlib import Path

from intentfence.offline_actions import digest

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ["review_id", "material_sha256", "untrusted_content", "review_status",
          "risk_label_review", "notes", "reviewer_id", "reviewed_at"]


def content_before_action(source, boundary):
    if type(boundary) is not int or not 0 < boundary <= len(source["conversation"]):
        raise ValueError("invalid boundary")
    messages = [(i, m) for i, m in enumerate(source["conversation"][:boundary]) if m["role"] == "tool_result"]
    if not messages:
        raise ValueError("no pre-action low-trust result")
    i, message = messages[-1]
    return i, message["content"]


def main():
    receipts = {}

    def read(rel, expected):
        data = (ROOT / rel).read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        if sha != expected:
            raise ValueError(f"changed input: {rel}")
        receipts[rel] = sha
        return data

    register = json.loads(read("data/interim/aib_action_evidence_20260911/register_v2.json",
        "b8c38e4d5942ddf52451be8300c4367e8eecd466961471dad475ed1d3dc435d2"))
    source = {r["id"]: r for r in map(json.loads, read(
        "data/raw/agent_injection_bench/data/agent_injection_bench.jsonl",
        "606cb74f5ce874dba45d9cdf591af678d7c6bd8a92ff3189d0f522fb39fb941e").splitlines())}
    materials, mapping = {}, {}
    for entry in register["entries"]:
        origin = entry["origin"]
        data = read(origin["source_file"], origin["source_file_sha256"])
        rows = [json.loads(data)] if origin["source_file"].endswith("/record.json") else list(map(json.loads, data.splitlines()))
        boundary = rows[origin["record_index"]]["conversation_boundary"]
        case = origin["case_id"]
        index, content = content_before_action(source[case], boundary)
        key = f"{case}:{index}"
        rid = "risk-" + digest({"scope": "20260912-risk", "key": key})[:20]
        materials[rid] = {"review_id": rid, "material_sha256": digest({"untrusted_content": content}),
                          "untrusted_content": content}
        mapping.setdefault(rid, {"source_id": case, "conversation_index": index, "action_keys": []})["action_keys"].append(entry["key"])
    if len(materials) != 14:
        raise ValueError("unexpected content coverage")
    out = ROOT / "data/interim/aib_risk_review_20260912"
    out.mkdir(exist_ok=False)
    files = {}
    for slot in ["A", "B"]:
        folder = out / f"reviewer_{slot}"
        folder.mkdir()
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(sorted(materials.values(), key=lambda r: digest({"slot": slot, "id": r["review_id"]})))
        data = stream.getvalue().encode("utf-8")
        parsed = list(csv.DictReader(io.StringIO(data.decode())))
        if len(parsed) != 14 or any(digest({"untrusted_content": r["untrusted_content"]}) != r["material_sha256"]
                                     or any(r[k] for k in FIELDS[3:]) for r in parsed):
            raise ValueError("CSV roundtrip mismatch or answers leaked")
        (folder / "risk.csv").write_bytes(data)
        files[f"reviewer_{slot}/risk.csv"] = hashlib.sha256(data).hexdigest()
    private = out / "coordinator_only"
    private.mkdir()
    (private / "mapping.json").write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8")
    manifest = {"files": files, "input_receipts": receipts, "contents": 14,
                "scope": "latest_pre_action_tool_result_only_not_entire_source_scenario",
                "training_ready": False, "labels_applied": 0,
                "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (private / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(files, indent=2))


if __name__ == "__main__":
    main()
