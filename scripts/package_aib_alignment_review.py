"""Build answer-free alignment forms; packaging alone does not establish blindness."""
import csv
import hashlib
import io
import json
from pathlib import Path

from intentfence.offline_actions import digest

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ["review_id", "material_sha256", "user_goal", "history_before_action",
          "source_tool_definitions", "proposed_action", "review_status",
          "task_alignment_label_review", "action_realism_review", "notes", "reviewer_id", "reviewed_at"]


def material(source, boundary, action):
    if type(boundary) is not int or not 0 < boundary <= len(source["conversation"]):
        raise ValueError("invalid boundary")
    history = [{"role": "system", "content": source["system_prompt"]}] + [
        {"role": m["role"], "content": m["content"]} for m in source["conversation"][:boundary]]
    users = [m["content"] for m in history if m["role"] == "user"]
    if not users:
        raise ValueError("missing user")
    return {"user_goal": users[-1], "history_before_action": history,
            "source_tool_definitions": source["tools_available"], "proposed_action": action}


def csv_bytes(rows, reviewer):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in sorted(rows, key=lambda r: digest({"reviewer_order": reviewer, "id": r["review_id"]})):
        writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                         for k, v in row.items()})
    return stream.getvalue().encode("utf-8")


def main():
    receipts = {}

    def read(rel, expected):
        data = (ROOT / rel).read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        if actual != expected:
            raise ValueError(f"changed input: {rel}")
        receipts[rel] = actual
        return data

    register = json.loads(read("data/interim/aib_action_evidence_20260911/register_v2.json",
        "b8c38e4d5942ddf52451be8300c4367e8eecd466961471dad475ed1d3dc435d2"))
    source = {r["id"]: r for r in map(json.loads, read(
        "data/raw/agent_injection_bench/data/agent_injection_bench.jsonl",
        "606cb74f5ce874dba45d9cdf591af678d7c6bd8a92ff3189d0f522fb39fb941e").splitlines())}
    rows, mapping = [], []
    for entry in register["entries"]:
        origin = entry["origin"]
        raw = read(origin["source_file"], origin["source_file_sha256"])
        originals = [json.loads(raw)] if origin["source_file"].endswith("/record.json") else list(map(json.loads, raw.splitlines()))
        record = originals[origin["record_index"]]
        observation = (record.get("observations") or [record["observation"]])[origin["observation_index"]]
        if observation != entry["original_observation"]:
            raise ValueError("observation binding mismatch")
        content = material(source[origin["case_id"]], record["conversation_boundary"], observation["candidate_action"])
        sha = digest(content)
        rid = "review-" + digest({"version": "alignment-20260912", "key": entry["key"]})[:20]
        rows.append({"review_id": rid, "material_sha256": sha, **content})
        mapping.append({"review_id": rid, "material_sha256": sha, "source_key": entry["key"],
                        "action_observation_id": entry["action_observation_id"], "origin": origin})
    if len(rows) != 23 or len({r["review_id"] for r in rows}) != 23:
        raise ValueError("review coverage mismatch")
    output = ROOT / "data/interim/aib_alignment_review_20260912"
    output.mkdir(exist_ok=False)
    files = {}
    for reviewer in ["A", "B"]:
        folder = output / f"reviewer_{reviewer}"
        folder.mkdir()
        data = csv_bytes(rows, reviewer)
        (folder / "alignment.csv").write_bytes(data)
        files[f"reviewer_{reviewer}/alignment.csv"] = hashlib.sha256(data).hexdigest()
        parsed = list(csv.DictReader(io.StringIO(data.decode("utf-8"))))
        if len(parsed) != 23 or any(any(r[k] for k in FIELDS[6:]) for r in parsed):
            raise ValueError("nonempty review fields or incomplete form")
        for parsed_row in parsed:
            restored = {k: json.loads(parsed_row[k]) if k != "user_goal" else parsed_row[k]
                        for k in ["user_goal", "history_before_action", "source_tool_definitions", "proposed_action"]}
            if digest(restored) != parsed_row["material_sha256"]:
                raise ValueError("CSV material roundtrip mismatch")
    private = output / "coordinator_only"
    private.mkdir()
    (private / "mapping.json").write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8")
    manifest = {"input_receipts": receipts, "reviewer_files": files, "observations": 23,
        "review_complete": False, "independence_verified": False, "training_ready": False,
        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (private / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(files, indent=2))


if __name__ == "__main__":
    main()
