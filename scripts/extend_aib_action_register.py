"""Append the verified git-log pair to the immutable AIB evidence register."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml

from intentfence.action_register_extension import extend_register
from intentfence.aib_gitlog_contrast import GitlogCase, build_gitlog_contrast
from intentfence.offline_actions import SourceBinding

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/aib_action_register_v3_20260923.yaml"


def source_path(rel: str) -> Path:
    path = (ROOT / rel).resolve()
    if ROOT not in path.parents:
        raise ValueError("input path outside workspace")
    return path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    if (config["scope"] != "append_quarantined_source_bound_observations"
            or any(config[key] is not False for key in (
                "training_ready", "human_verified", "labels_applied", "construct_splits"
            ))):
        raise ValueError("register scope mismatch")
    base_path = source_path(config["base_path"])
    record_path = source_path(config["new_record_path"])
    manifest_path = source_path(config["new_manifest_path"])
    for path, expected in (
        (base_path, config["base_sha256"]),
        (record_path, config["new_record_sha256"]),
        (manifest_path, config["new_manifest_sha256"]),
    ):
        if sha(path) != expected:
            raise ValueError(f"changed input: {path}")
    base = json.loads(base_path.read_text(encoding="utf-8"))
    if base["observations"] != config["expected_old_observations"]:
        raise ValueError("unexpected historical register size")
    for rel, expected in base["input_hashes"].items():
        if sha(source_path(rel)) != expected:
            raise ValueError(f"changed historical input: {rel}")
    if sha(ROOT / "src/intentfence/action_evidence_adapter.py") != base["adapter_sha256"]:
        raise ValueError("historical adapter changed")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest["record_sha256"] != config["new_record_sha256"]
            or manifest["cases"] != 1 or manifest["observations"] != 2
            or any(manifest[key] is not False for key in (
                "training_ready", "human_verified", "labels_applied"
            ))):
        raise ValueError("new manifest boundary mismatch")
    for rel, expected in manifest["input_sha256"].items():
        if sha(source_path(rel)) != expected:
            raise ValueError(f"changed new input: {rel}")
    source_config = yaml.safe_load(source_path(config["source_config_path"]).read_text(
        encoding="utf-8"
    ))
    if source_config["case_id"] != config["expected_case_id"]:
        raise ValueError("new case ID mismatch")
    source = source_path(source_config["source_path"]).read_bytes()
    matching = [raw for raw in source.splitlines()
                if json.loads(raw)["id"] == config["expected_case_id"]]
    if len(matching) != 1:
        raise ValueError("new source row missing or duplicated")
    case = GitlogCase.model_validate({
        "source": SourceBinding(
            revision=source_config["source_revision"],
            file_sha256=source_config["source_sha256"],
            row_sha256=source_config["row_sha256"],
            case_id=source_config["case_id"],
        ).model_dump(),
        "conversation_boundary": source_config["conversation_boundary"],
        "user_goal": source_config["user_goal"],
        "attack_evidence": source_config["attack_evidence"],
        "file_path": source_config["file_path"],
        "file_content": source_config["file_content"],
        "preparation_author": source_config["preparation_author"],
    })
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if build_gitlog_contrast(matching[0], case) != record:
        raise ValueError("new record differs from source-bound replay")
    implementations = {
        rel: manifest["input_sha256"][rel] for rel in (
            "src/intentfence/aib_gitlog_contrast.py",
            "src/intentfence/offline_actions.py",
        )
    }
    result = extend_register(
        base, record, source_file=config["new_record_path"],
        source_sha256=config["new_record_sha256"],
        implementation_hashes=implementations,
    )
    if result["observations"] != config["expected_new_observations"]:
        raise ValueError("unexpected expanded register size")
    result["base_register_sha256"] = config["base_sha256"]
    result["added_record_sha256"] = config["new_record_sha256"]
    result["added_manifest_sha256"] = config["new_manifest_sha256"]
    result["extension_config_sha256"] = sha(CONFIG)
    result["extension_implementation_sha256"] = sha(Path(__file__))
    result["extension_logic_sha256"] = sha(
        ROOT / "src/intentfence/action_register_extension.py"
    )
    result["input_hashes"][config["base_path"]] = config["base_sha256"]
    result["input_hashes"][config["new_record_path"]] = config["new_record_sha256"]
    result["input_hashes"][config["new_manifest_path"]] = config["new_manifest_sha256"]
    output = source_path(config["output_path"])
    allowed = (ROOT / "data/interim/aib_action_evidence_20260923").resolve()
    if output.parent != allowed:
        raise ValueError("output outside register directory")
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.verify:
        if output.read_bytes() != rendered.encode("utf-8"):
            raise ValueError("saved register differs from source-bound replay")
        print("Verified expanded AIB evidence register and source hashes.")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(rendered)
        print(json.dumps({"observations": result["observations"],
                          "added": len(result["entries"]) - len(base["entries"]),
                          "sha256": hashlib.sha256(rendered.encode()).hexdigest()}))


if __name__ == "__main__":
    main()
