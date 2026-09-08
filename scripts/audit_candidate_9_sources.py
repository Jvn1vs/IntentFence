"""Audit pinned candidate 9 inputs; no model execution or dataset mutation."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import unicodedata
from pathlib import Path
from typing import Any

import yaml


def normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def overlap(rows: list[dict[str, Any]], tests: list[dict[str, Any]], key: str) -> dict:
    known = {normalized(row[key]) for row in tests}
    if any(not normalized(row[key]) for row in rows + tests):
        raise ValueError(f"Empty isolation key: {key}")
    matched = sum(normalized(row[key]) in known for row in rows)
    return {"rows": len(rows), "overlapping_rows": matched, "remaining_rows": len(rows) - matched}


def jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def audit(root: Path) -> dict[str, Any]:
    raw = root / "data/raw"
    manifest_path = raw / "source_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pinned = yaml.safe_load((root / "configs/upstream_sources.yaml").read_text(encoding="utf-8"))
    sources = {}
    for name in ("bipia", "injecagent"):
        entries = [entry for entry in manifest["sources"] if entry["name"] == name]
        if len(entries) != 1:
            raise ValueError(f"Expected exactly one source entry: {name}")
        source = entries[0]
        checkout = raw / name
        head = subprocess.check_output(
            ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True
        ).strip()
        if head != source["revision"] or head != pinned["sources"][name]["revision"]:
            raise ValueError(f"Revision mismatch: {name}")
        for entry in source["files"]:
            path = (checkout / entry["path"]).resolve()
            if not path.is_relative_to(checkout.resolve()):
                raise ValueError("Source path escapes checkout")
            content = path.read_bytes()
            if len(content) != entry["size"] or hashlib.sha256(content).hexdigest() != entry["sha256"]:
                raise ValueError(f"Source changed: {path}")
        sources[name] = {
            "revision": head, "verified_files": len(source["files"]),
            "license_finding": source["license_finding"],
        }
    tasks = {}
    for task in ("email", "table", "code"):
        rows = jsonl(raw / f"bipia/benchmark/{task}/train.jsonl")
        contexts = [json.dumps(row["context"], ensure_ascii=False) for row in rows]
        tasks[task] = {
            "official_train_rows": len(rows),
            "unique_normalized_contexts": len({normalized(value) for value in contexts}),
            "fields": sorted(set.intersection(*(set(row) for row in rows))),
        }
    tests = []
    for kind in ("dh", "ds"):
        for setting in ("base", "enhanced"):
            tests.extend(json.loads(
                (raw / f"injecagent/data/test_cases_{kind}_{setting}.json").read_text(encoding="utf-8")
            ))
    atomic = {}
    for kind in ("dh", "ds"):
        atomic[kind] = overlap(
            jsonl(raw / f"injecagent/data/attacker_cases_{kind}.jsonl"), tests, "Attacker Instruction"
        )
    atomic["user"] = overlap(jsonl(raw / "injecagent/data/user_cases.jsonl"), tests, "User Instruction")
    return {
        "schema_version": 1, "execution_owner": "codex", "status": "source_audit_only",
        "source_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "sources": sources, "bipia": tasks, "injecagent_atomic_overlap": atomic,
        "overlap_method": "NFKC/casefold/whitespace-normalized exact instruction equality",
        "limitation": "Non-overlap does not certify semantic, tool-pair or near-duplicate isolation.",
        "training_ready": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    result = audit(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
