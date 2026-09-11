"""Conservative must-link graph over pinned AI scenario notes, not split creation."""

import hashlib
import json
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def components(ids: list[str], groups: list[list[str]]) -> list[list[str]]:
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate source ID")
    parent = {key: key for key in ids}

    def find(key):
        while parent[key] != key:
            key = parent[key]
        return key

    for group in groups:
        if not group or any(key not in parent for key in group):
            raise ValueError("empty group or unknown source")
        for key in group[1:]:
            left, right = find(group[0]), find(key)
            parent[max(left, right)] = min(left, right)
    result = defaultdict(list)
    for key in sorted(ids):
        result[find(key)].append(key)
    return sorted(result.values())


def main():
    config_path = ROOT / "configs/aib_family_constraints_20260911.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    source = ROOT / "data/interim/aib_scenarios_20260911/aggregate/reviews.jsonl"
    content = source.read_bytes()
    if hashlib.sha256(content).hexdigest() != config["review_sha256"]:
        raise ValueError("review snapshot changed")
    rows = [json.loads(s) for s in content.splitlines()]
    by_name = defaultdict(list)
    for row in rows:
        by_name[row["provisional_scenario_review"]["family"]].append(row["source_id"])
    groups = list(by_name.values()) if config["link_equal_provisional_names"] else []
    groups += [entry["members"] for entry in config["manual_links"]]
    result = components([row["source_id"] for row in rows], groups)
    report = {
        "review_sha256": config["review_sha256"],
        "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "source_cases": len(rows), "provisional_names": len(by_name),
        "constraint_components": len(result), "components": result,
        "manual_links": config["manual_links"],
        "reviewer": "Codex/AI", "human_verified": False,
        "family_isolation_complete": False, "split": None, "training_ready": False,
    }
    output = ROOT / "data/interim/aib_family_constraints_20260911"
    output.mkdir(exist_ok=False)
    with (output / "constraints.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"cases": len(rows), "names": len(by_name), "components": len(result),
                      "sha256": hashlib.sha256((output / "constraints.json").read_bytes()).hexdigest()}))


if __name__ == "__main__":
    main()
