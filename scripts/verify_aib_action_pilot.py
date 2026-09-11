"""Read-only verification of pilot file hashes and literal source parameter spans."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def main() -> None:
    config_path = ROOT / "configs/aib_action_pilot_20260911.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    output = ROOT / config["output_dir"]
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    checks = {
        "config_sha256": config_path,
        "source_sha256": ROOT / config["source_path"],
        "preparation_sha256": ROOT / config["preparation_path"],
        "records_sha256": output / "observations.jsonl",
        "builder_sha256": ROOT / "scripts/build_aib_action_pilot.py",
        "binding_implementation_sha256": ROOT / "src/intentfence/aib_pilot.py",
    }
    for key, path in checks.items():
        if sha(path) != manifest[key]:
            raise ValueError(f"manifest hash mismatch: {key}")
    rows = {json.loads(line)["id"]: line for line in checks["source_sha256"].read_bytes().splitlines()}
    records = [json.loads(line) for line in checks["records_sha256"].read_text(encoding="utf-8").splitlines()]
    if sorted(r["case_id"] for r in records) != sorted(config["case_ids"]):
        raise ValueError("record membership mismatch")
    count = 0
    for record in records:
        row_bytes = rows[record["case_id"]]
        row = json.loads(row_bytes)
        prefix = [row["system_prompt"]] + [
            m["content"] for m in row["conversation"][:record["conversation_boundary"]]]
        for key in ["risk_label", "task_alignment_label", "split"]:
            if record[key] is not None:
                raise ValueError("labels or split applied")
        for trace in record["observations"]:
            count += 1
            body = {k: v for k, v in trace.items() if k != "action_observation_id"}
            if canonical_sha(body) != trace["action_observation_id"]:
                raise ValueError("observation digest mismatch")
            if trace["implementation_sha256"] != sha(ROOT / "src/intentfence/offline_actions.py"):
                raise ValueError("policy implementation changed")
            if trace["source_binding"]["row_sha256"] != hashlib.sha256(row_bytes).hexdigest():
                raise ValueError("row binding mismatch")
            for key in ["executed", "external_side_effects", "human_verified", "training_ready"]:
                if trace[key] is not False:
                    raise ValueError("evidence boundary changed")
            arguments = trace["candidate_action"]["arguments"]
            if set(arguments) != set(trace["field_provenance"]):
                raise ValueError("parameter provenance missing")
            for parameter, value in arguments.items():
                span = trace["field_provenance"][parameter]["span"]
                if not 0 <= span["message"] < len(prefix):
                    raise ValueError("parameter points outside source prefix")
                text = prefix[span["message"]]
                if not 0 <= span["start"] < span["end"] <= len(text):
                    raise ValueError("invalid source span")
                if text[span["start"]:span["end"]] != value:
                    raise ValueError("argument differs from source literal")
    if count != manifest["observations"] or len(records) != manifest["cases"]:
        raise ValueError("count mismatch")
    print(json.dumps({"status": "verified_literal_provenance_not_semantic_labels",
                      "cases": len(records), "observations": count,
                      "manifest_sha256": sha(output / "manifest.json")}, indent=2))


if __name__ == "__main__":
    main()
