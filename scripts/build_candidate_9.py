"""Build a versioned candidate from pinned train sources, preserving test locks."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
from pathlib import Path

import yaml
from audit_candidate_9_sources import audit, jsonl

from intentfence.candidate9 import build, norm


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/candidate_9.yaml"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    if args.output.exists():
        raise FileExistsError("Refusing to overwrite candidate directory")
    source_audit = audit(root)
    locked = []
    bindings = {}

    def read_rows(relative: str) -> list[dict]:
        path = root / relative
        bindings[relative] = file_hash(path)
        return jsonl(path)

    for relative in config["locked_inputs"]:
        locked.extend(row["untrusted_content"] for row in read_rows(relative))
    contexts = []
    for task in config["tasks"]:
        if task not in ("email", "table"):
            raise ValueError("Only reviewed Email/Table field profiles are enabled")
        relative = f"data/raw/bipia/benchmark/{task}/train.jsonl"
        for i, row in enumerate(read_rows(relative), 1):
            contexts.append(
                {
                    "goal": row["question"],
                    "content": row["context"],
                    "task": task,
                    "source_record": f"{relative}:{i}",
                }
            )
        locked.extend(
            row["context"] for row in read_rows(f"data/raw/bipia/benchmark/{task}/test.jsonl")
        )
    attack_path = root / "data/raw/bipia/benchmark/text_attack_train.json"
    test_attack_path = root / "data/raw/bipia/benchmark/text_attack_test.json"
    for path in (
        attack_path,
        test_attack_path,
        args.config.resolve(),
        root / "data/raw/source_manifest.json",
    ):
        bindings[str(path.relative_to(root))] = file_hash(path)
    attacks = json.loads(attack_path.read_text(encoding="utf-8"))
    test_attacks = json.loads(test_attack_path.read_text(encoding="utf-8"))
    locked.extend(text for values in test_attacks.values() for text in values)
    hard = read_rows(config["hard_negatives"])
    print("Verified inputs; constructing isolated groups and samples.", flush=True)
    rows, stats = build(
        contexts, attacks, hard, locked, {norm(name) for name in test_attacks}, config
    )
    for relative, expected in bindings.items():
        if file_hash(root / relative) != expected:
            raise ValueError(f"Input changed during construction: {relative}")
    args.output.mkdir(parents=True, exist_ok=False)
    files = {}
    for role in config["split_ratios"]:
        subset = [row for row in rows if row["split"] == role]
        path = args.output / f"{role}.jsonl"
        with path.open("x", encoding="utf-8") as handle:
            for row in subset:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        files[role] = {"path": path.name, "rows": len(subset), "sha256": file_hash(path)}
    # Stratified train/validation review only; calibration/test content is not sampled for tuning.
    review = []
    for role in ("train", "validation"):
        for kind in ("clean", "attack", "hard_negative"):
            bucket = [
                row for row in rows if row["split"] == role and row["construction_kind"] == kind
            ]
            for row in bucket[:20]:
                review.append(dict(row, reviewer_id=None, review_decision=None))
    review_path = args.output / "label_review.jsonl"
    with review_path.open("x", encoding="utf-8") as handle:
        for row in review:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    manifest = {
        "schema_version": 1,
        "candidate": config["candidate"],
        "status": "constructed_unreviewed",
        "execution_owner": "codex",
        "python": platform.python_version(),
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip(),
        "implementation_sha256": {
            name: file_hash(root / name)
            for name in (
                "src/intentfence/candidate9.py",
                "scripts/build_candidate_9.py",
                "scripts/audit_candidate_9_sources.py",
            )
        },
        "config": config,
        "inputs": bindings,
        "source_audit": source_audit,
        "files": files,
        "quality": stats,
        "review": {"path": review_path.name, "rows": len(review), "sha256": file_hash(review_path)},
        "formal_training_authorized": False,
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
