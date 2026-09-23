"""Build or verify the fixed AIB git-log action contrast without executing tools."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml

from intentfence.aib_gitlog_contrast import GitlogCase, build_gitlog_contrast
from intentfence.offline_actions import SourceBinding

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/aib_gitlog_contrast_20260923.yaml"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    if (config["owner_approved"] is not True
            or config["approval_scope"] != "existing_approved_aib_source_and_autonomous_data_engineering"
            or any(config[key] is not False for key in (
                "train_models", "apply_training_labels", "construct_splits", "execute_source_tools"
            ))):
        raise ValueError("stage boundary mismatch")
    source_path = ROOT / config["source_path"]
    source = source_path.read_bytes()
    if hashlib.sha256(source).hexdigest() != config["source_sha256"]:
        raise ValueError("source file hash mismatch")
    matching = [raw for raw in source.splitlines()
                if json.loads(raw)["id"] == config["case_id"]]
    if len(matching) != 1:
        raise ValueError("source ID missing or duplicated")
    case = GitlogCase.model_validate({
        "source": SourceBinding(
            revision=config["source_revision"],
            file_sha256=config["source_sha256"],
            row_sha256=config["row_sha256"],
            case_id=config["case_id"],
        ).model_dump(),
        "conversation_boundary": config["conversation_boundary"],
        "user_goal": config["user_goal"],
        "attack_evidence": config["attack_evidence"],
        "file_path": config["file_path"],
        "file_content": config["file_content"],
        "preparation_author": config["preparation_author"],
    })
    record = build_gitlog_contrast(matching[0], case)
    if record != build_gitlog_contrast(matching[0], case):
        raise ValueError("deterministic replay failed")
    if sha(source_path) != config["source_sha256"]:
        raise ValueError("source changed during build")
    output = (ROOT / config["output_dir"]).resolve()
    allowed = (ROOT / "data/interim/aib_gitlog_contrast_20260923").resolve()
    if allowed not in output.parents:
        raise ValueError("output outside pilot directory")
    record_text = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
    inputs = [CONFIG, source_path, Path(__file__),
              ROOT / "src/intentfence/aib_gitlog_contrast.py",
              ROOT / "src/intentfence/offline_actions.py"]
    manifest = {
        "input_sha256": {str(path.relative_to(ROOT)).replace("\\", "/"): sha(path)
                         for path in inputs},
        "record_sha256": hashlib.sha256(record_text.encode("utf-8")).hexdigest(),
        "cases": 1,
        "observations": 2,
        "source_bound_replay": True,
        "training_ready": False,
        "human_verified": False,
        "labels_applied": False,
    }
    if args.verify:
        if (output / "record.jsonl").read_bytes() != record_text.encode("utf-8"):
            raise ValueError("saved record differs from replay")
        if json.loads((output / "manifest.json").read_text(encoding="utf-8")) != manifest:
            raise ValueError("manifest differs from current inputs")
        print("Verified source-bound git-log contrast and input hashes.")
    else:
        output.mkdir(parents=True, exist_ok=False)
        with (output / "record.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(record_text)
        with (output / "manifest.json").open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
