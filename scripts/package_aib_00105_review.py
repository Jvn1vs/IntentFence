"""Create answer-free supplemental Risk and Alignment forms for one AIB case."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

import yaml

from intentfence.offline_actions import digest
from scripts.package_aib_alignment_review import FIELDS as ALIGNMENT_FIELDS
from scripts.package_aib_alignment_review import csv_bytes, material
from scripts.package_aib_risk_review import FIELDS as RISK_FIELDS
from scripts.package_aib_risk_review import content_before_action

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/aib_00105_review_package_20260923.yaml"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def review_materials(source: dict, record: dict, entries: list[dict]) -> tuple[list[dict], dict]:
    """Select exactly one action pair and one pre-action content for blinded forms."""
    if len(entries) != 2 or len({entry["key"] for entry in entries}) != 2:
        raise ValueError("expected two distinct action entries")
    if any(entry["origin"]["case_id"] != source["id"]
           or entry["origin"]["record_index"] != 0
           or entry["origin"]["observation_index"] != index
           or entry["original_observation"] != record["observations"][index]
           for index, entry in enumerate(entries)):
        raise ValueError("entry does not match source observation")
    alignment, mapping = [], []
    for entry in entries:
        content = material(
            source, record["conversation_boundary"], entry["proposed_action"]
        )
        rid = "review-" + digest({
            "version": "aib-00105-alignment-20260923", "key": entry["key"]
        })[:20]
        alignment.append({"review_id": rid, "material_sha256": digest(content), **content})
        mapping.append({"review_id": rid, "material_sha256": digest(content),
                        "source_key": entry["key"],
                        "action_observation_id": entry["action_observation_id"]})
    index, low_trust = content_before_action(source, record["conversation_boundary"])
    risk = {"review_id": "risk-" + digest({
        "version": "aib-00105-risk-20260923", "case": source["id"], "index": index
    })[:20], "material_sha256": digest({"untrusted_content": low_trust}),
        "untrusted_content": low_trust}
    return alignment, {"risk": risk, "alignment_mapping": mapping,
                       "risk_mapping": {"source_id": source["id"],
                                        "conversation_index": index,
                                        "action_keys": [entry["key"] for entry in entries]}}


def risk_csv(row: dict, reviewer: str) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=RISK_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerow(row)
    data = stream.getvalue().encode("utf-8")
    parsed = list(csv.DictReader(io.StringIO(data.decode("utf-8"))))
    if (len(parsed) != 1 or parsed[0]["review_id"] != row["review_id"]
            or digest({"untrusted_content": parsed[0]["untrusted_content"]})
            != parsed[0]["material_sha256"]
            or any(parsed[0][key] for key in RISK_FIELDS[3:])):
        raise ValueError(f"invalid Risk form for reviewer {reviewer}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--refresh-manifest", action="store_true")
    args = parser.parse_args()
    if args.verify and args.refresh_manifest:
        raise ValueError("choose verify or refresh-manifest")
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    if (config["scope"] != "answer_free_supplemental_review_materials_only"
            or any(config[key] is not False for key in (
                "review_complete", "independence_verified", "human_verified", "training_ready"
            ))):
        raise ValueError("review package scope mismatch")
    for key, checksum in (
        ("register_path", "register_sha256"),
        ("source_path", "source_sha256"),
        ("record_path", "record_sha256"),
    ):
        if sha(ROOT / config[key]) != config[checksum]:
            raise ValueError(f"changed input: {key}")
    register = json.loads((ROOT / config["register_path"]).read_text(encoding="utf-8"))
    if register["training_ready"] is not False:
        raise ValueError("register unexpectedly training-ready")
    selected = [entry for entry in register["entries"] if entry["key"] in config["action_keys"]]
    selected.sort(key=lambda entry: config["action_keys"].index(entry["key"]))
    if [entry["key"] for entry in selected] != config["action_keys"]:
        raise ValueError("missing selected observation")
    raw_rows = [json.loads(raw) for raw in (ROOT / config["source_path"]).read_bytes().splitlines()]
    sources = [row for row in raw_rows if row["id"] == config["case_id"]]
    if len(sources) != 1:
        raise ValueError("source case missing or duplicated")
    record = json.loads((ROOT / config["record_path"]).read_text(encoding="utf-8"))
    if record["source_binding"]["case_id"] != config["case_id"]:
        raise ValueError("record source ID mismatch")
    if any(entry["origin"]["source_file_sha256"] != config["record_sha256"]
           for entry in selected):
        raise ValueError("register origin hash mismatch")
    alignment, supplement = review_materials(sources[0], record, selected)
    output = (ROOT / config["output_dir"]).resolve()
    allowed = (ROOT / "data/interim/aib_00105_review_20260923").resolve()
    if output != allowed:
        raise ValueError("output outside review directory")
    files = {}
    file_data = {}
    for task in ("alignment", "risk"):
        for reviewer in ("A", "B"):
            data = (csv_bytes(alignment, reviewer) if task == "alignment"
                    else risk_csv(supplement["risk"], reviewer))
            if task == "alignment":
                parsed = list(csv.DictReader(io.StringIO(data.decode("utf-8"))))
                if len(parsed) != 2 or any(any(row[key] for key in ALIGNMENT_FIELDS[6:])
                                           for row in parsed):
                    raise ValueError("invalid answer-free Alignment form")
                for row in parsed:
                    content = {key: json.loads(row[key]) if key != "user_goal" else row[key]
                               for key in ("user_goal", "history_before_action",
                                           "source_tool_definitions", "proposed_action")}
                    if digest(content) != row["material_sha256"]:
                        raise ValueError("Alignment material roundtrip mismatch")
            rel = f"{task}/reviewer_{reviewer}/{task}.csv"
            file_data[rel] = data
            files[rel] = hashlib.sha256(data).hexdigest()
    mapping_text = json.dumps({
        "alignment": supplement["alignment_mapping"],
        "risk": supplement["risk_mapping"],
    }, ensure_ascii=False, indent=2) + "\n"
    manifest = {"input_sha256": {config[key]: config[checksum] for key, checksum in (
        ("register_path", "register_sha256"), ("source_path", "source_sha256"),
        ("record_path", "record_sha256"))},
        "config_sha256": sha(CONFIG),
        "implementation_sha256": sha(Path(__file__)),
        "helper_sha256": {
            "scripts/package_aib_alignment_review.py": sha(
                ROOT / "scripts/package_aib_alignment_review.py"
            ),
            "scripts/package_aib_risk_review.py": sha(
                ROOT / "scripts/package_aib_risk_review.py"
            ),
        },
        "reviewer_files": files,
        "alignment_actions": 2, "risk_contents": 1,
        "review_complete": False, "independence_verified": False,
        "human_verified": False, "training_ready": False}
    manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    if args.verify or args.refresh_manifest:
        for rel, data in file_data.items():
            if (output / rel).read_bytes() != data:
                raise ValueError(f"reviewer file differs from replay: {rel}")
        if (output / "coordinator_only/mapping.json").read_text(
            encoding="utf-8"
        ) != mapping_text:
            raise ValueError("review mapping differs from replay")
        if args.refresh_manifest:
            (output / "coordinator_only/manifest.json").write_text(
                manifest_text, encoding="utf-8"
            )
        elif (output / "coordinator_only/manifest.json").read_text(
            encoding="utf-8"
        ) != manifest_text:
            raise ValueError("review manifest differs from replay")
    else:
        output.mkdir(parents=True, exist_ok=False)
        for rel, data in file_data.items():
            path = output / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        private = output / "coordinator_only"
        private.mkdir()
        (private / "mapping.json").write_text(mapping_text, encoding="utf-8")
        (private / "manifest.json").write_text(manifest_text, encoding="utf-8")
    print(json.dumps(files, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
