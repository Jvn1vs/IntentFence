"""Build the approved source-literal risk contrast pilot, or verify saved records."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml

from intentfence.aib_risk_pilot import RiskPilotCase, build_contrast

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/aib_risk_pilot_20260911.yaml"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    if config["owner_approved"] is not True:
        raise ValueError("stage approval missing")
    source_path = ROOT / config["source_path"]
    source = source_path.read_bytes()
    if hashlib.sha256(source).hexdigest() != config["source_sha256"]:
        raise ValueError("source file hash mismatch")
    rows = {}
    for line in source.splitlines():
        row = json.loads(line)
        if row["id"] in rows:
            raise ValueError("duplicate source ID")
        rows[row["id"]] = line
    preparation = ROOT / config["preparation_path"]
    if sha(preparation) != config["preparation_sha256"]:
        raise ValueError("preparation file hash mismatch")
    cases = [RiskPilotCase.model_validate(c) for c in json.loads(
        preparation.read_text(encoding="utf-8"))]
    if sorted(c.source.case_id for c in cases) != sorted(config["case_ids"]):
        raise ValueError("case membership mismatch")
    for case in cases:
        if (case.source.file_sha256 != config["source_sha256"]
                or case.source.revision != config["source_revision"]):
            raise ValueError("source binding mismatch")
    results = [build_contrast(rows[c.source.case_id], c) for c in cases]
    if results != [build_contrast(rows[c.source.case_id], c) for c in cases]:
        raise ValueError("deterministic replay failed")
    if sha(source_path) != config["source_sha256"]:
        raise ValueError("source changed")
    output = (ROOT / config["output_dir"]).resolve()
    allowed = (ROOT / "data/interim/aib_risk_pilot_20260911").resolve()
    if allowed not in output.parents:
        raise ValueError("output outside pilot directory")
    records = "".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in results)
    hashes = {str(p.relative_to(ROOT)).replace("\\", "/"): sha(p) for p in [
        CONFIG, preparation, source_path, Path(__file__),
        ROOT / "src/intentfence/aib_risk_pilot.py",
        ROOT / "src/intentfence/offline_actions.py",
    ]}
    manifest = {"hashes": hashes, "records_sha256": hashlib.sha256(records.encode()).hexdigest(),
                "cases": len(results),
                "proposals": sum(len(r["observations"]) for r in results),
                "contrast_pairs": len(results),
                "deterministic_replay_passed": True, "source_unchanged": True,
                "training_ready": False, "human_verified": False, "labels_applied": False}
    if args.verify:
        if (output / "records.jsonl").read_bytes() != records.encode():
            raise ValueError("saved records differ from source-bound replay")
        if json.loads((output / "manifest.json").read_text(encoding="utf-8")) != manifest:
            raise ValueError("manifest differs from current evidence")
        print("Verified source-bound replay and all file hashes.")
    else:
        output.mkdir(parents=True, exist_ok=False)
        with (output / "records.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(records)
        with (output / "manifest.json").open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
