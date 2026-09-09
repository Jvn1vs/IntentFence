"""Check v3 isolation and re-derive every Dolly row's source identity/content."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from audit_candidate_9_sources import jsonl
from verify_candidate_9 import verify

from intentfence.candidate9_sources import dolly_backgrounds


def check_dolly_rows(rows: list[dict], backgrounds: list[dict], attacks: dict) -> int:
    lookup = {row["source_record"]: row for row in backgrounds}
    count = 0
    for row in rows:
        record_id = row["source_record_id"]
        is_dolly = record_id.startswith("databricks/databricks-dolly-15k@")
        if not is_dolly:
            if row["source"] == "DatabricksDolly15k":
                raise ValueError("Dolly source label on a different source record")
            continue
        if record_id not in lookup:
            raise ValueError("Unknown Dolly record")
        original = lookup[record_id]
        if (
            row["source"] != "DatabricksDolly15k"
            or row["scenario"] != original["task"]
            or row["user_goal"] != original["goal"].strip()
            or row["source_attribution"] != original["attribution"]
        ):
            raise ValueError("Dolly provenance/goal mismatch")
        if row["construction_kind"] == "clean":
            expected = [original["content"].strip()]
        elif row["construction_kind"] == "attack":
            family = row["attack_family"]
            if family not in attacks:
                raise ValueError("Unknown source attack family")
            if row["insertion_position"] == "start":
                expected = [
                    (text + "\n\n" + original["content"]).strip() for text in attacks[family]
                ]
            elif row["insertion_position"] == "end":
                expected = [
                    (original["content"] + "\n\n" + text).strip() for text in attacks[family]
                ]
            else:
                raise ValueError("Unknown attack insertion position")
        else:
            raise ValueError("Dolly background mislabeled as authored hard negative")
        if row["untrusted_content"] not in expected:
            raise ValueError("Dolly text cannot be reconstructed from pinned source")
        count += 1
    if not count:
        raise ValueError("No Dolly samples in v3")
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    result = verify(args.directory, root)
    manifest = json.loads((args.directory / "manifest.json").read_text(encoding="utf-8"))
    source = manifest["dolly_source_manifest"]["source"]
    backgrounds, _ = dolly_backgrounds(jsonl(root / "data/raw/dolly" / source["data_file"]))
    rows = [
        row
        for evidence in manifest["files"].values()
        for row in jsonl(args.directory / evidence["path"])
    ]
    attacks = json.loads(
        (root / "data/raw/bipia/benchmark/text_attack_train.json").read_text(encoding="utf-8")
    )
    result["dolly_rows_reconstructed"] = check_dolly_rows(rows, backgrounds, attacks)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
