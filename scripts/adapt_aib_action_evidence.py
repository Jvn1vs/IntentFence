"""Adapt all six frozen AIB pilot batches into a separate evidence register."""
import hashlib
import json
from pathlib import Path

from intentfence.action_evidence_adapter import EvidenceOrigin, adapt
from scripts.verify_aib_action_prereview import EXPECTED

ROOT = Path(__file__).resolve().parents[1]


def main():
    hashes = {}

    def read(rel, expected=None):
        path = (ROOT / rel).resolve()
        if ROOT not in path.parents:
            raise ValueError("input outside workspace")
        data = path.read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        if expected is not None and actual != expected:
            raise ValueError(f"changed input: {rel}")
        hashes[rel] = actual
        return data

    review = json.loads(read("data/interim/aib_action_prereview_20260911/review.json", EXPECTED))
    inputs = review["input_receipts"] + [{"path": "data/interim/aib_flight_contrast_20260911/record.json",
        "sha256": "71dee53c314843c7dd715e981ef5a8ae435a9bf18eafde6327cbb3896807a4db"}]
    entries = []
    keys = set()
    for item in inputs:
        rel = item["path"]
        data = read(rel, item["sha256"])
        rows = [json.loads(data)] if rel.endswith("/record.json") else list(map(json.loads, data.splitlines()))
        for ri, row in enumerate(rows):
            case = row.get("case_id") or row.get("source_id") or row["source_binding"]["case_id"]
            for oi, observation in enumerate(row.get("observations") or [row["observation"]]):
                implementation = row.get("code_sha256") or row.get("implementation_hashes")
                if implementation is None:
                    if "aib_action_pilot_" in rel:
                        implementation = {"src/intentfence/offline_actions.py": observation["implementation_sha256"]}
                    elif "aib_communication_pilot_" in rel:
                        implementation = {"src/intentfence/communication_actions.py": observation["implementation_sha256"],
                            "src/intentfence/offline_actions.py": observation["shared_contract_sha256"]}
                    else:
                        implementation = {"src/intentfence/aib_risk_pilot.py": row["implementation_sha256"],
                            "src/intentfence/offline_actions.py": row["shared_contract_sha256"]}
                implementation = {k.replace("\\", "/"): v for k, v in implementation.items()}
                for path, expected in implementation.items():
                    read(path, expected)
                key = f"{case}:{oi}"
                if key in keys:
                    raise ValueError("duplicate observation key")
                keys.add(key)
                entry = adapt(observation, EvidenceOrigin(source_file=rel, source_file_sha256=item["sha256"],
                    record_index=ri, observation_index=oi, case_id=case, implementation_hashes=implementation))
                entry["key"] = key
                entries.append(entry)
    if len(entries) != 23 or len({e["action_observation_id"] for e in entries}) != 23:
        raise ValueError("unexpected observation coverage")
    result = {"entries": entries, "input_hashes": hashes, "observations": len(entries),
              "training_ready": False, "route_b_admission_verified": False,
              "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "adapter_sha256": hashlib.sha256((ROOT / "src/intentfence/action_evidence_adapter.py").read_bytes()).hexdigest()}
    out = ROOT / "data/interim/aib_action_evidence_20260911/register_v2.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print("observations", len(entries), "sha256", hashlib.sha256(out.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
