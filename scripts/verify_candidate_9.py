"""Independently check candidate files, provenance bindings and split isolation."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from intentfence.candidate9 import SimilarityIndex, digest
from intentfence.schema import IntentSample


def verify(directory: Path, root: Path) -> dict:
    manifest_path = directory / "manifest.json"
    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if (directory / ".complete").read_text().strip() != manifest_hash:
        raise ValueError("Manifest completion hash mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for relative, expected in {**manifest["inputs"], **manifest["implementation_sha256"]}.items():
        path = (root / relative).resolve()
        if (
            not path.is_relative_to(root.resolve())
            or hashlib.sha256(path.read_bytes()).hexdigest() != expected
        ):
            raise ValueError(f"Input/implementation hash mismatch: {relative}")
    rows = []
    role_counts = {}
    for role, evidence in manifest["files"].items():
        path = (directory / evidence["path"]).resolve()
        if not path.is_relative_to(directory.resolve()):
            raise ValueError("Output path escapes candidate directory")
        if hashlib.sha256(path.read_bytes()).hexdigest() != evidence["sha256"]:
            raise ValueError(f"Output hash mismatch: {role}")
        subset = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        if len(subset) != evidence["rows"] or any(row["split"] != role for row in subset):
            raise ValueError(f"Row count/split mismatch: {role}")
        role_counts[role] = dict(Counter(row["construction_kind"] for row in subset))
        rows.extend(subset)
    ids = set()
    groups = defaultdict(set)
    families = defaultdict(set)
    for row in rows:
        IntentSample.model_validate(row)
        expected = "c9_" + digest(row["user_goal"] + "\n" + row["untrusted_content"])
        if row["sample_id"] != expected or expected in ids:
            raise ValueError("Invalid or duplicate sample id")
        ids.add(expected)
        if (
            row["human_verified"]
            or row["task_alignment_label"] is not None
            or row["proposed_action"]
        ):
            raise ValueError("Unexpected reviewed label/action claim")
        groups[row["template_group"]].add(row["split"])
        if row["attack_family_group"]:
            families[row["attack_family_group"]].add(row["split"])
    if any(len(value) != 1 for value in list(groups.values()) + list(families.values())):
        raise ValueError("Background/attack family crosses roles")
    config = manifest["config"]
    locked_texts = []
    protected_paths = list(config["locked_inputs"]) + [
        f"data/raw/bipia/benchmark/{task}/test.jsonl" for task in config["tasks"]
    ]
    for relative in protected_paths:
        for line in (root / relative).read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            locked_texts.append(item.get("untrusted_content", item.get("context")))
    official_attacks = json.loads(
        (root / "data/raw/bipia/benchmark/text_attack_test.json").read_text(encoding="utf-8")
    )
    locked_texts.extend(text for values in official_attacks.values() for text in values)
    locked_index = SimilarityIndex(
        locked_texts, config["shingle_chars"], config["near_duplicate_jaccard"]
    )
    if any(locked_index.matches(row["untrusted_content"]) for row in rows):
        raise ValueError("Candidate text overlaps protected evaluation/calibration input")
    index = SimilarityIndex(
        [row["untrusted_content"] for row in rows],
        config["shingle_chars"],
        config["near_duplicate_jaccard"],
    )
    for i, row in enumerate(rows):
        if any(
            rows[j]["split"] != row["split"]
            for j in index.matches(row["untrusted_content"])
            if j < i
        ):
            raise ValueError("Generated content near-duplicate crosses roles")
    if role_counts != manifest["quality"]["splits"]:
        raise ValueError("Reported quality counts mismatch")
    review = manifest["review"]
    path = directory / review["path"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != review["sha256"]:
        raise ValueError("Review file changed")
    review_rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if len(review_rows) != review["rows"] or any(
        row["sample_id"] not in ids or row["split"] not in ("train", "validation")
        for row in review_rows
    ):
        raise ValueError("Invalid review sample membership/role")
    if manifest["formal_training_authorized"] or manifest["quality"]["training_ready"]:
        raise ValueError("Unreviewed candidate may not claim training readiness")
    return {
        "status": "integrity_verified_not_training_ready",
        "rows": len(rows),
        "manifest_sha256": manifest_hash,
        "splits": role_counts,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.directory, Path(__file__).resolve().parents[1]), indent=2))
