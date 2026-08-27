from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from pathlib import Path
from typing import Any

from intentfence.data import file_sha256

PROTOCOL_VERSION = "2.1.0-ai-draft.2"
IMMUTABLE_FIELDS = (
    "audit_id",
    "sample_id",
    "split",
    "scenario",
    "user_goal",
    "untrusted_content",
    "proposed_action",
)
REVIEW_FIELDS = (
    "task_alignment_label_review",
    "action_realism_review",
    "review_status",
    "reviewer",
    "reviewed_at",
    "notes",
)
ALL_FIELDS = IMMUTABLE_FIELDS + REVIEW_FIELDS


def _prompt_path() -> Path:
    return Path(__file__).resolve().parents[1] / "docs" / "route_b_third_ai_review_prompt.md"


def _read_alignment_sheet(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        expected = (
            "audit_id",
            "sample_id",
            "split",
            "scenario",
            "user_goal",
            "untrusted_content",
            "proposed_action",
            "task_alignment_label_review",
            "action_realism_review",
            "review_status",
            "reviewer",
            "reviewed_at",
            "notes",
        )
        if tuple(reader.fieldnames or ()) != expected:
            raise ValueError(f"unexpected Alignment sheet columns: {path}")
        rows = list(reader)
    if len(rows) != 400:
        raise ValueError(
            f"third AI package requires exactly 400 Alignment rows; observed {len(rows)}"
        )
    if len({row["audit_id"] for row in rows}) != len(rows):
        raise ValueError("source Alignment sheet contains duplicate audit_id values")
    return rows


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ALL_FIELDS, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def build_package(source_dir: Path, output_dir: Path, *, seed: int = 342) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite third AI package: {output_dir}")
    source_sheet = source_dir / "reviewer_a_alignment.csv"
    source_audit_manifest = source_dir / "audit_manifest.json"
    if not source_sheet.is_file() or not source_audit_manifest.is_file():
        raise FileNotFoundError(
            "source dual-AI package must contain reviewer_a_alignment.csv and audit_manifest.json"
        )

    source_rows = _read_alignment_sheet(source_sheet)
    rows = [
        {
            **{field: source_row[field] for field in IMMUTABLE_FIELDS},
            **{field: "" for field in REVIEW_FIELDS},
        }
        for source_row in source_rows
    ]
    random.Random(f"{seed}:alignment:reviewer_c").shuffle(rows)

    output_dir.mkdir(parents=True)
    sheet_path = output_dir / "reviewer_c_alignment.csv"
    _write_csv(sheet_path, rows)
    prompt_path = output_dir / "reviewer_c_prompt.md"
    prompt_path.write_text(_prompt_path().read_text(encoding="utf-8"), encoding="utf-8")

    source_manifest_hash = file_sha256(source_audit_manifest)
    prompt_hash = file_sha256(prompt_path)
    package_manifest = {
        "schema_version": 1,
        "status": "awaiting_third_ai_submission_not_training_authorized",
        "protocol_version": PROTOCOL_VERSION,
        "review_mode": "dual_ai_plus_third_supplementary_alignment",
        "reviewer_slot": "ai_c",
        "alignment_rows": len(rows),
        "seed": seed,
        "source_dual_ai_package": {
            "path": str(source_dir.resolve()),
            "audit_manifest_sha256": source_manifest_hash,
            "source_alignment_sheet_sha256": file_sha256(source_sheet),
        },
        "submission": {
            "sheet": {
                "path": sheet_path.name,
                "sha256": file_sha256(sheet_path),
                "labels_exposed": False,
            },
            "prompt": {"path": prompt_path.name, "sha256": prompt_hash},
            "seed_labels_included": False,
            "prior_reviewer_outputs_included": False,
        },
        "constraints": {
            "review_all_rows_not_only_prior_disagreements": True,
            "prior_dual_ai_failure_must_be_preserved": True,
            "formal_training_authorized": False,
            "human_verified": False,
        },
    }
    serialized = json.dumps(
        package_manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    package_manifest["sha256"] = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    (output_dir / "third_ai_package_manifest.json").write_text(
        json.dumps(package_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest_example = {
        "schema_version": 1,
        "protocol_version": PROTOCOL_VERSION,
        "review_mode": "dual_ai_plus_third_supplementary_alignment",
        "content_class": "synthetic_project_owned",
        "external_upload_approved_by_project_owner": False,
        "source_dual_ai_audit_manifest_sha256": source_manifest_hash,
        "third_ai_package_manifest_sha256": package_manifest["sha256"],
        "reviewer_c": {
            "reviewer_id": "provider_c:model_c@revision_c",
            "provider": "REPLACE",
            "model": "REPLACE",
            "revision": "REPLACE",
            "execution_mode": "local_or_external",
            "temperature": 0,
            "prompt_sha256": prompt_hash,
            "seed_labels_hidden": True,
            "prior_reviewer_outputs_hidden": True,
            "raw_output_path": "reviewer_c_alignment.csv",
            "raw_output_sha256": file_sha256(sheet_path),
        },
        "formal_training_authorized": False,
        "human_verified": False,
    }
    (output_dir / "ai_c_review_manifest.example.json").write_text(
        json.dumps(manifest_example, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    readme = "\n".join(
        (
            "# Third AI Alignment package",
            "",
            "This package is a supplementary full review by reviewer C; it is not an adjudication package.",
            "",
            "- Review only `reviewer_c_alignment.csv`.",
            "- Do not share `sealed_seed_labels.json` or prior reviewer outputs.",
            "- Use `reviewer_c_prompt.md`; record provider/model/revision and output hash in `ai_c_review_manifest.json`.",
            "- Review all 400 rows, not only the 13 prior disagreements.",
            "- Preserve existing AI A/B results and keep `formal_training_authorized=false`.",
            "- Do not edit the input sheet to make it agree with another reviewer.",
            "",
        )
    )
    (output_dir / "README.md").write_text(readme, encoding="utf-8")
    return {"output_dir": str(output_dir.resolve()), "manifest": package_manifest}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a blinded third-AI Route B Alignment package"
    )
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=342)
    args = parser.parse_args()
    print(
        json.dumps(
            build_package(args.source_dir, args.output_dir, seed=args.seed),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
