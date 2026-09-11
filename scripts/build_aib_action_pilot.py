"""Build only the owner-approved, isolated AIB action pilot; no training export."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from intentfence.aib_pilot import PilotCase, bind_and_select

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/aib_action_pilot_20260911.yaml"


def main() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    if config["owner_approved"] is not True or config["scope"] != "quarantined_source_pilot":
        raise ValueError("pilot approval missing")
    source = ROOT / config["source_path"]
    content = source.read_bytes()
    source_hash = hashlib.sha256(content).hexdigest()
    if source_hash != config["source_sha256"]:
        raise ValueError("source file hash mismatch")
    rows = {}
    for line in content.splitlines():
        row = json.loads(line)
        if row["id"] in rows:
            raise ValueError("duplicate source ID")
        rows[row["id"]] = line
    plan_path = ROOT / config["preparation_path"]
    plan_bytes = plan_path.read_bytes()
    if hashlib.sha256(plan_bytes).hexdigest() != config["preparation_sha256"]:
        raise ValueError("preparation hash mismatch")
    plan = json.loads(plan_bytes)
    cases = [PilotCase.model_validate(c) for c in plan["cases"]]
    if len(cases) != len(config["case_ids"]) or {c.case_id for c in cases} != set(config["case_ids"]):
        raise ValueError("case membership mismatch")
    if sorted(e["case_id"] for e in plan["excluded"]) != sorted(config["excluded_case_ids"]):
        raise ValueError("exclusion membership mismatch")
    results = [bind_and_select(rows[c.case_id], c, revision=config["source_revision"],
                               source_hash=source_hash) for c in cases]
    # Replay before writing and verify that policies never mutate their input.
    replay = [bind_and_select(rows[c.case_id], c, revision=config["source_revision"],
                             source_hash=source_hash) for c in cases]
    if replay != results or hashlib.sha256(source.read_bytes()).hexdigest() != source_hash:
        raise ValueError("replay or source immutability failed")
    output = (ROOT / config["output_dir"]).resolve()
    allowed = (ROOT / "data/interim/aib_action_pilot_20260911").resolve()
    if output == allowed or allowed not in output.parents:
        raise ValueError("output must be a new child of the isolated pilot directory")
    output.mkdir(parents=True, exist_ok=False)
    records = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in results)
    with (output / "observations.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(records)
    manifest = {
        "scope": config["scope"], "source_revision": config["source_revision"],
        "source_sha256": source_hash, "preparation_sha256": config["preparation_sha256"],
        "config_sha256": hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
        "builder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "binding_implementation_sha256": hashlib.sha256(
            (ROOT / "src/intentfence/aib_pilot.py").read_bytes()).hexdigest(),
        "records_sha256": hashlib.sha256(records.encode("utf-8")).hexdigest(),
        "cases": len(results),
        "observations": sum(len(r["observations"]) for r in results),
        "excluded": plan["excluded"], "deterministic_replay_passed": True,
        "source_unchanged": True, "training_ready": False, "human_verified": False,
        "split": None, "labels_applied": False,
    }
    with (output / "manifest.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
