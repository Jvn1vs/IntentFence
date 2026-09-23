"""Extend the frozen AIB must-link graph without rewriting its historical file."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml

if __package__:
    from .build_aib_family_constraints import components
else:
    from build_aib_family_constraints import components

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/aib_family_supplement_20260923.yaml"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extend(base: dict, links: list[dict]) -> list[list[str]]:
    """Union old components with explicit new links; reject malformed evidence."""
    if (base.get("family_isolation_complete") is not False
            or base.get("training_ready") is not False or base.get("split") is not None):
        raise ValueError("base graph must remain quarantined")
    old = base["components"]
    ids = [member for group in old for member in group]
    if (len(ids) != base["source_cases"] or len(set(ids)) != len(ids)
            or any(not group for group in old)):
        raise ValueError("invalid base components")
    if not links:
        raise ValueError("missing supplemental links")
    groups = list(old)
    for link in links:
        members = link["members"]
        if len(members) < 2 or len(set(members)) != len(members) or not link["reason"]:
            raise ValueError("invalid supplemental link")
        groups.append(members)
    return components(ids, groups)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    if (config["scope"] != "additional_conservative_must_link_not_split_clearance"
            or any(config[key] is not False for key in (
                "human_verified", "family_isolation_complete", "construct_splits", "training_ready"
            ))):
        raise ValueError("supplement scope mismatch")
    base_path = ROOT / config["base_path"]
    source_path = ROOT / config["source_path"]
    if sha(base_path) != config["base_sha256"] or sha(source_path) != config["source_sha256"]:
        raise ValueError("input hash mismatch")
    base = json.loads(base_path.read_text(encoding="utf-8"))
    if set(config["source_row_sha256"]) != {
        member for link in config["manual_links"] for member in link["members"]
    }:
        raise ValueError("source row membership mismatch")
    found = {}
    for raw in source_path.read_bytes().splitlines():
        row_id = json.loads(raw)["id"]
        if row_id in config["source_row_sha256"]:
            if row_id in found:
                raise ValueError("duplicate source row")
            found[row_id] = hashlib.sha256(raw).hexdigest()
    if found != config["source_row_sha256"]:
        raise ValueError("source row hash mismatch")
    updated = extend(base, config["manual_links"])
    report = {
        "base_sha256": config["base_sha256"],
        "source_sha256": config["source_sha256"],
        "source_revision": config["source_revision"],
        "source_row_sha256": found,
        "config_sha256": sha(CONFIG),
        "implementation_sha256": sha(Path(__file__)),
        "components_implementation_sha256": sha(
            ROOT / "scripts/build_aib_family_constraints.py"
        ),
        "source_cases": base["source_cases"],
        "constraint_components": len(updated),
        "components": updated,
        "new_manual_links": config["manual_links"],
        "reviewer": "Codex/AI",
        "human_verified": False,
        "family_isolation_complete": False,
        "split": None,
        "training_ready": False,
    }
    output = (ROOT / config["output_path"]).resolve()
    allowed = (ROOT / "data/interim/aib_family_supplement_20260923").resolve()
    if output.parent != allowed:
        raise ValueError("output outside supplement directory")
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.verify:
        if output.read_bytes() != rendered.encode("utf-8"):
            raise ValueError("saved supplement differs from replay")
        print("Verified supplemented family graph and input hashes.")
    else:
        output.parent.mkdir(parents=True, exist_ok=False)
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(rendered)
        print(json.dumps({"source_cases": base["source_cases"],
                          "old_components": base["constraint_components"],
                          "new_components": len(updated),
                          "sha256": hashlib.sha256(rendered.encode()).hexdigest()}))


if __name__ == "__main__":
    main()
