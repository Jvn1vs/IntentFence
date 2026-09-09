"""Extend the grouped candidate with approved Dolly contexts, without changing v2."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import subprocess
import time
from collections import Counter
from pathlib import Path

import yaml
from audit_candidate_9_sources import audit, jsonl
from build_candidate_9 import file_hash

from intentfence.candidate9 import build, norm
from intentfence.candidate9_sources import DOLLY_REVISION, dolly_backgrounds

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    started = time.monotonic()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/candidate_9_v3.yaml"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    bindings = {}

    def bind(relative: str) -> Path:
        path = (ROOT / relative).resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError("Input path escapes project")
        bindings[str(path.relative_to(ROOT))] = file_hash(path)
        return path

    extension = yaml.safe_load(bind(str(args.config)).read_text(encoding="utf-8"))
    config = yaml.safe_load(bind(extension["base_config"]).read_text(encoding="utf-8"))
    config["candidate"] = extension["candidate"]
    config["locked_inputs"] += extension["additional_locked_inputs"]
    proposals_path = bind(extension["source_proposals"])
    source = yaml.safe_load(proposals_path.read_text(encoding="utf-8"))["sources"]["dolly_contexts"]
    if source["owner_approved"] is not True or source["revision"] != DOLLY_REVISION:
        raise ValueError("Missing matching Dolly source approval")
    source_manifest_path = bind(extension["dolly_manifest"])
    dolly_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    if dolly_manifest["source"] != source or dolly_manifest["approval_file_sha256"] != file_hash(
        proposals_path
    ):
        raise ValueError("Downloaded Dolly source does not match approval")
    for filename, evidence in dolly_manifest["files"].items():
        path = bind(str((source_manifest_path.parent / filename).relative_to(ROOT)))
        if path.stat().st_size != evidence["size"] or file_hash(path) != evidence["sha256"]:
            raise ValueError("Dolly source bytes changed")
    dolly_raw = jsonl(source_manifest_path.parent / source["data_file"])
    dolly, exclusions = dolly_backgrounds(dolly_raw)
    source_audit = audit(ROOT)
    bind("data/raw/source_manifest.json")
    locked = []
    for relative in config["locked_inputs"]:
        locked.extend(row["untrusted_content"] for row in jsonl(bind(relative)))
    contexts = []
    for task in config["tasks"]:
        relative = f"data/raw/bipia/benchmark/{task}/train.jsonl"
        contexts.extend(
            {
                "goal": row["question"],
                "content": row["context"],
                "task": task,
                "source": "BIPIA",
                "source_record": f"{relative}:{i}",
            }
            for i, row in enumerate(jsonl(bind(relative)), 1)
        )
        locked.extend(
            row["context"] for row in jsonl(bind(f"data/raw/bipia/benchmark/{task}/test.jsonl"))
        )
    contexts.extend(dolly)
    attacks = json.loads(
        bind("data/raw/bipia/benchmark/text_attack_train.json").read_text(encoding="utf-8")
    )
    test_attacks = json.loads(
        bind("data/raw/bipia/benchmark/text_attack_test.json").read_text(encoding="utf-8")
    )
    locked.extend(text for values in test_attacks.values() for text in values)
    hard = jsonl(bind(config["hard_negatives"]))
    print(
        f"Verified {len(dolly_raw)} Dolly rows; selected {len(dolly)} grounded contexts. Building groups...",
        flush=True,
    )
    rows, stats = build(
        contexts, attacks, hard, locked, {norm(name) for name in test_attacks}, config
    )
    source_by_record = {row["source_record"]: row["source"] for row in contexts}
    for row in rows:
        if row["source_record_id"] in source_by_record:
            row["source"] = source_by_record[row["source_record_id"]]
    stats["dolly_selection"] = {
        "raw_rows": len(dolly_raw),
        "selected_backgrounds": len(dolly),
        "exclusions": exclusions,
    }
    stats["sources_by_split"] = {
        role: dict(Counter(row["source"] for row in rows if row["split"] == role))
        for role in config["split_ratios"]
    }
    stats["scenarios_by_split"] = {
        role: dict(Counter(row["scenario"] for row in rows if row["split"] == role))
        for role in config["split_ratios"]
    }
    stats["limitations"] = [
        item for item in stats["limitations"] if not item.startswith("BIPIA is the only")
    ]
    stats["limitations"] += [
        "Two public background sources; attack expressions still derive from BIPIA",
        "Dolly official train only; every new holdout is project-derived",
        "Hard negatives remain a small AI-authored unreviewed pool",
    ]
    for relative, expected in bindings.items():
        if file_hash(ROOT / relative) != expected:
            raise ValueError(f"Input changed during construction: {relative}")
    args.output.mkdir(parents=True, exist_ok=False)

    def save(name: str, values: list[dict]) -> dict:
        path = args.output / name
        with path.open("x", encoding="utf-8") as handle:
            for value in values:
                handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
        return {"path": name, "rows": len(values), "sha256": file_hash(path)}

    files = {
        role: save(f"{role}.jsonl", [row for row in rows if row["split"] == role])
        for role in config["split_ratios"]
    }
    review = []
    for role in ("train", "validation"):
        for name in sorted({row["source"] for row in rows}):
            for kind in ("clean", "attack", "hard_negative"):
                subset = [
                    row
                    for row in rows
                    if (row["split"], row["source"], row["construction_kind"]) == (role, name, kind)
                ]
                review.extend(
                    dict(row, reviewer_id=None, review_decision=None)
                    for row in subset[: extension["review_per_source_kind_role"]]
                )
    review_evidence = save("label_review.jsonl", review)
    implementations = [
        "src/intentfence/candidate9.py",
        "src/intentfence/candidate9_sources.py",
        "scripts/build_candidate_9_v3.py",
        "scripts/build_candidate_9.py",
        "scripts/audit_candidate_9_sources.py",
    ]
    manifest = {
        "schema_version": 1,
        "candidate": config["candidate"],
        "status": "constructed_unreviewed",
        "execution_owner": "codex",
        "python": platform.python_version(),
        "dependencies": {name: importlib.metadata.version(name) for name in ("pydantic", "PyYAML")},
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "implementation_sha256": {name: file_hash(ROOT / name) for name in implementations},
        "inputs": bindings,
        "config": config,
        "extension": extension,
        "source_audit": source_audit,
        "dolly_source_manifest": dolly_manifest,
        "files": files,
        "review": review_evidence,
        "quality": stats,
        "formal_training_authorized": False,
        "build_seconds": round(time.monotonic() - started, 3),
    }
    with (args.output / "manifest.json").open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    (args.output / ".complete").write_text(
        file_hash(args.output / "manifest.json") + "\n", encoding="utf-8"
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
