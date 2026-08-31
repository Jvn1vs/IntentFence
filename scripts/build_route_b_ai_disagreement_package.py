"""Build and validate a project-owner package for dual-AI disagreements."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from intentfence.data import file_sha256

AI_PROTOCOL_VERSION = "2.1.0-ai-draft.1"
AI_REVIEW_MODE = "dual_ai_engineering"
AI_EVIDENCE_STATUS = "ai_reviewed_engineering_only"
AI_ANALYSIS_STATUS = "ai_quality_gates_failed_engineering_only"
AUDIT_MANIFEST_STATUS = "awaiting_two_independent_reviewers_not_training_authorized"
PACKAGE_STATUS = "awaiting_project_owner_ai_disagreement_adjudication"

RISK_FIELDS = (
    "audit_id",
    "sample_id",
    "split",
    "scenario",
    "user_goal",
    "untrusted_content",
    "risk_label_review",
    "review_status",
    "reviewer",
    "reviewed_at",
    "notes",
)
ALIGNMENT_FIELDS = (
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
RISK_IMMUTABLE_FIELDS = RISK_FIELDS[:6]
ALIGNMENT_IMMUTABLE_FIELDS = ALIGNMENT_FIELDS[:7]
RISK_LABELS = {
    "benign",
    "instruction_hijacking",
    "data_exfiltration",
    "privilege_escalation",
    "tool_manipulation",
}
ALIGNMENT_LABELS = {"aligned", "unrelated", "ambiguous", "malicious"}
REALISM_LABELS = {"realistic", "unrealistic"}
SOURCE_EVIDENCE_KEYS = {
    "audit_manifest",
    "ai_review_manifest",
    "ai_review_analysis",
    "reviewer_a_risk",
    "reviewer_b_risk",
    "reviewer_a_alignment",
    "reviewer_b_alignment",
}
PACKAGE_FILES = {
    "README.md",
    "adjudication_manifest.json",
    "risk_disagreement_adjudication.csv",
    "alignment_disagreement_adjudication.csv",
    "submission_receipt.json",
}

RISK_OUTPUT_FIELDS = (
    *RISK_IMMUTABLE_FIELDS,
    "ai_a_risk_label",
    "ai_a_status",
    "ai_a_reviewer",
    "ai_a_reviewed_at",
    "ai_a_notes",
    "ai_b_risk_label",
    "ai_b_status",
    "ai_b_reviewer",
    "ai_b_reviewed_at",
    "ai_b_notes",
    "disagreement_fields",
    "final_risk_label",
    "adjudication_status",
    "adjudicator_id",
    "adjudicated_at",
    "rationale",
)
ALIGNMENT_OUTPUT_FIELDS = (
    *ALIGNMENT_IMMUTABLE_FIELDS,
    "ai_a_task_alignment_label",
    "ai_a_action_realism",
    "ai_a_status",
    "ai_a_reviewer",
    "ai_a_reviewed_at",
    "ai_a_notes",
    "ai_b_task_alignment_label",
    "ai_b_action_realism",
    "ai_b_status",
    "ai_b_reviewer",
    "ai_b_reviewed_at",
    "ai_b_notes",
    "disagreement_fields",
    "final_task_alignment_label",
    "final_action_realism",
    "adjudication_status",
    "adjudicator_id",
    "adjudicated_at",
    "rationale",
)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def _read_csv(
    path: Path,
    fields: tuple[str, ...],
    *,
    allow_empty: bool = False,
) -> list[dict[str, str]]:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            with path.open(encoding=encoding, newline="") as handle:
                reader = csv.DictReader(handle)
                if tuple(reader.fieldnames or ()) != fields:
                    raise ValueError(f"unexpected columns in {path}")
                rows = list(reader)
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            last_error = exc
            continue
        if not rows and not allow_empty:
            raise ValueError(f"CSV is empty: {path}")
        ids = [row["audit_id"] for row in rows]
        if any(not value for value in ids) or len(set(ids)) != len(ids):
            raise ValueError(f"audit_id values must be unique and non-empty: {path}")
        return rows
    raise ValueError(str(last_error))


def _reviewer_id(rows: list[dict[str, str]], path: Path) -> str:
    if not rows:
        raise ValueError(f"CSV is empty: {path}")
    ids = {row["reviewer"].strip() for row in rows}
    if len(ids) != 1 or not next(iter(ids), ""):
        raise ValueError(f"every AI row in {path} must use one non-empty reviewer ID")
    if any(row["review_status"] != "completed" for row in rows):
        raise ValueError(f"all AI rows in {path} must have review_status=completed")
    if any(not row["reviewed_at"].strip() for row in rows):
        raise ValueError(f"all AI rows in {path} must have reviewed_at")
    return next(iter(ids))


def _source_binding(path: Path) -> dict[str, str]:
    return {"path": str(path.resolve()), "sha256": file_sha256(path)}


def _canonical_sha256(payload: dict[str, Any], field: str = "sha256") -> str:
    body = dict(payload)
    body.pop(field, None)
    return hashlib.sha256(
        json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        )
    ).hexdigest()


def _require_sha256(value: Any, description: str) -> str:
    digest = str(value or "")
    if len(digest) != 64:
        raise ValueError(f"{description} must be a 64-character SHA-256 digest")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ValueError(f"{description} must be a hexadecimal SHA-256 digest") from exc
    return digest.lower()


def _resolve_declared_path(raw_path: Any, *, base_dir: Path, description: str) -> Path:
    value = str(raw_path or "").strip()
    if not value:
        raise ValueError(f"{description} path is missing")
    path = Path(value)
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _assert_declared_file_binding(
    declaration: dict[str, Any],
    *,
    expected_path: Path,
    description: str,
    hash_key: str = "sha256",
) -> None:
    declared_path = _resolve_declared_path(
        declaration.get("path"), base_dir=expected_path.parent, description=description
    )
    if declared_path != expected_path.resolve():
        raise ValueError(f"{description} path does not match input")
    declared_hash = _require_sha256(declaration.get(hash_key), f"{description} {hash_key}")
    if declared_hash != file_sha256(expected_path):
        raise ValueError(f"{description} hash does not match input")


def _validate_audit_manifest(
    path: Path,
    *,
    expected_risk_rows: int,
    expected_alignment_rows: int,
) -> dict[str, Any]:
    manifest = _read_json(path)
    if manifest.get("schema_version") != 1:
        raise ValueError("audit manifest schema_version must be 1")
    if manifest.get("review_mode") != AI_REVIEW_MODE:
        raise ValueError("audit manifest review_mode must be dual_ai_engineering")
    if manifest.get("risk_rows") != expected_risk_rows:
        raise ValueError("audit manifest Risk row count does not match AI source sheets")
    if manifest.get("alignment_rows") != expected_alignment_rows:
        raise ValueError("audit manifest Alignment row count does not match AI source sheets")
    if manifest.get("formal_training_authorized") is not False:
        raise ValueError("audit manifest must keep formal_training_authorized=false")
    if manifest.get("status") != AUDIT_MANIFEST_STATUS:
        raise ValueError("audit manifest status is not the expected locked review status")
    sealed = manifest.get("sealed_seed_labels")
    if not isinstance(sealed, dict):
        raise ValueError("audit manifest sealed_seed_labels declaration is missing")
    _resolve_declared_path(
        sealed.get("path"), base_dir=path.parent, description="audit manifest sealed_seed_labels"
    )
    _require_sha256(sealed.get("sha256"), "audit manifest sealed_seed_labels sha256")
    claimed = _require_sha256(manifest.get("sha256"), "audit manifest sha256")
    if claimed != _canonical_sha256(manifest):
        raise ValueError("audit manifest self-hash mismatch")
    return manifest


def _assert_ai_manifest_binding(
    ai_manifest_path: Path,
    *,
    audit_manifest_path: Path,
    paths: dict[str, Path],
) -> dict[str, Any]:
    manifest = _read_json(ai_manifest_path)
    if manifest.get("schema_version") != 1:
        raise ValueError("AI review manifest schema_version must be 1")
    if manifest.get("protocol_version") != AI_PROTOCOL_VERSION:
        raise ValueError("AI review manifest protocol_version is unsupported")
    if manifest.get("review_mode") != AI_REVIEW_MODE:
        raise ValueError("AI review manifest review_mode must be dual_ai_engineering")
    if manifest.get("content_class") != "synthetic_project_owned":
        raise ValueError("AI review manifest content_class must be synthetic_project_owned")
    if manifest.get("supplementary_evidence_only") is not True:
        raise ValueError("AI review manifest must declare supplementary_evidence_only=true")
    if manifest.get("human_verified") is not False:
        raise ValueError("AI review manifest must keep human_verified=false")
    if manifest.get("formal_training_authorized") is not False:
        raise ValueError("AI review manifest must keep formal_training_authorized=false")
    if manifest.get("audit_manifest_sha256") != file_sha256(audit_manifest_path):
        raise ValueError("AI review manifest is not bound to the audit manifest hash")
    reviewers = manifest.get("reviewers")
    if not isinstance(reviewers, dict) or set(reviewers) != {"ai_a", "ai_b"}:
        raise ValueError("AI review manifest must define exactly ai_a and ai_b reviewers")
    for slot, task_paths in (
        ("ai_a", {"risk": paths["ai_a_risk"], "alignment": paths["ai_a_alignment"]}),
        ("ai_b", {"risk": paths["ai_b_risk"], "alignment": paths["ai_b_alignment"]}),
    ):
        reviewer = reviewers.get(slot)
        if not isinstance(reviewer, dict):
            raise ValueError(f"AI review manifest is missing {slot}")
        if not str(reviewer.get("reviewer_id", "")).strip():
            raise ValueError(f"AI review manifest {slot} reviewer_id is missing")
        raw_files = reviewer.get("raw_output_files")
        if not isinstance(raw_files, dict):
            raise ValueError(f"AI review manifest is missing {slot} raw_output_files")
        for task, path in task_paths.items():
            raw_path = Path(str(raw_files.get(f"{task}_path", "")))
            if not raw_path.is_absolute():
                raw_path = ai_manifest_path.parent / raw_path
            if raw_path.resolve() != path.resolve():
                raise ValueError(f"AI manifest {slot} {task} path does not match input")
            if raw_files.get(f"{task}_sha256") != file_sha256(path):
                raise ValueError(f"AI manifest {slot} {task} hash does not match input")
    return manifest


def _assert_provenance_bundle(
    *,
    audit_manifest_path: Path,
    ai_manifest_path: Path,
    analysis_path: Path,
    audit_manifest: dict[str, Any],
    ai_manifest: dict[str, Any],
    analysis: dict[str, Any],
    reviewer_ids: dict[str, str],
    risk_rows: int,
    alignment_rows: int,
) -> None:
    if analysis.get("schema_version") != 1:
        raise ValueError("AI review analysis schema_version must be 1")
    if analysis.get("protocol_version") != ai_manifest.get("protocol_version"):
        raise ValueError("AI review analysis protocol_version differs from AI manifest")
    if analysis.get("protocol_version") != AI_PROTOCOL_VERSION:
        raise ValueError("AI review analysis protocol_version is unsupported")
    if analysis.get("review_mode") != AI_REVIEW_MODE:
        raise ValueError("AI review analysis review_mode must be dual_ai_engineering")
    if analysis.get("evidence_status") != AI_EVIDENCE_STATUS:
        raise ValueError("AI review analysis must be marked as AI engineering evidence")
    if analysis.get("status") != AI_ANALYSIS_STATUS:
        raise ValueError("AI review analysis must preserve the failed engineering-only status")
    if analysis.get("quality_gates_passed") is not False:
        raise ValueError("AI review analysis quality_gates_passed must be false")
    if analysis.get("human_verified") is not False:
        raise ValueError("AI review analysis must keep human_verified=false")
    if analysis.get("formal_training_authorized") is not False:
        raise ValueError("AI review analysis must keep formal_training_authorized=false")
    analysis_manifest = analysis.get("ai_review_manifest")
    if not isinstance(analysis_manifest, dict):
        raise ValueError("AI review analysis is missing ai_review_manifest binding")
    _assert_declared_file_binding(
        analysis_manifest,
        expected_path=ai_manifest_path,
        description="AI review analysis ai_review_manifest",
    )
    analysis_audit = analysis.get("audit_manifest")
    if not isinstance(analysis_audit, dict):
        raise ValueError("AI review analysis is missing audit_manifest binding")
    _assert_declared_file_binding(
        analysis_audit,
        expected_path=audit_manifest_path,
        description="AI review analysis audit_manifest",
    )
    if _require_sha256(analysis_audit.get("sealed_sha256"), "AI review analysis audit_manifest sealed_sha256") != audit_manifest[
        "sha256"
    ].lower():
        raise ValueError("AI review analysis audit_manifest sealed hash differs from audit manifest")
    declared_ids = analysis.get("ai_reviewer_ids")
    if declared_ids != {
        "reviewer_a": reviewer_ids["ai_a"],
        "reviewer_b": reviewer_ids["ai_b"],
    }:
        raise ValueError("AI review analysis reviewer IDs differ from source AI sheets")
    manifest_reviewers = ai_manifest["reviewers"]
    if {
        "ai_a": str(manifest_reviewers["ai_a"].get("reviewer_id", "")).strip(),
        "ai_b": str(manifest_reviewers["ai_b"].get("reviewer_id", "")).strip(),
    } != reviewer_ids:
        raise ValueError("AI review manifest reviewer IDs differ from source AI sheets")
    if audit_manifest.get("risk_rows") != risk_rows or audit_manifest.get("alignment_rows") != alignment_rows:
        raise ValueError("audit manifest row counts differ from source AI sheets")
    if not isinstance(audit_manifest.get("sheets"), dict):
        raise ValueError("audit manifest sheets declaration is missing")
    if set(audit_manifest["sheets"]) != {
        "reviewer_a_risk.csv",
        "reviewer_b_risk.csv",
        "reviewer_a_alignment.csv",
        "reviewer_b_alignment.csv",
    }:
        raise ValueError("audit manifest must declare the four audit sheets")
    for declaration in audit_manifest["sheets"].values():
        if not isinstance(declaration, dict):
            raise ValueError("audit manifest sheet declaration is invalid")
        _require_sha256(declaration.get("sha256"), "audit manifest sheet sha256")
        if declaration.get("labels_exposed") is not False:
            raise ValueError("audit manifest sheet labels_exposed must remain false")
    if Path(analysis_path).resolve() == Path(ai_manifest_path).resolve():
        raise ValueError("AI review analysis must be a separate evidence file")


def _validate_ai_source_values(
    *,
    risk_a: list[dict[str, str]],
    risk_b: list[dict[str, str]],
    alignment_a: list[dict[str, str]],
    alignment_b: list[dict[str, str]],
    reviewer_ids: dict[str, str],
) -> None:
    for slot, rows, expected_id in (
        ("ai_a", risk_a, reviewer_ids["ai_a"]),
        ("ai_b", risk_b, reviewer_ids["ai_b"]),
        ("ai_a", alignment_a, reviewer_ids["ai_a"]),
        ("ai_b", alignment_b, reviewer_ids["ai_b"]),
    ):
        if any(row["reviewer"] != expected_id for row in rows):
            raise ValueError(f"{slot} reviewer ID differs between Risk and Alignment source sheets")
    for rows in (risk_a, risk_b):
        if any(row["risk_label_review"] not in RISK_LABELS for row in rows):
            raise ValueError("AI Risk labels must use the exact five-label vocabulary")
    for rows in (alignment_a, alignment_b):
        if any(
            row["task_alignment_label_review"] not in ALIGNMENT_LABELS
            or row["action_realism_review"] not in REALISM_LABELS
            for row in rows
        ):
            raise ValueError("AI Alignment labels and action realism must use exact vocabularies")


def _merge_risk(
    left_rows: list[dict[str, str]],
    right_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    left, right = ({row["audit_id"]: row for row in rows} for rows in (left_rows, right_rows))
    if set(left) != set(right):
        raise ValueError("AI Risk sheets have different audit_id sets")
    output: list[dict[str, str]] = []
    for audit_id in sorted(left):
        first, second = left[audit_id], right[audit_id]
        if any(first[field] != second[field] for field in RISK_IMMUTABLE_FIELDS):
            raise ValueError(f"immutable Risk content differs for audit_id={audit_id}")
        if first["risk_label_review"] == second["risk_label_review"]:
            continue
        output.append(
            {
                **{field: first[field] for field in RISK_IMMUTABLE_FIELDS},
                "ai_a_risk_label": first["risk_label_review"],
                "ai_a_status": first["review_status"],
                "ai_a_reviewer": first["reviewer"],
                "ai_a_reviewed_at": first["reviewed_at"],
                "ai_a_notes": first["notes"],
                "ai_b_risk_label": second["risk_label_review"],
                "ai_b_status": second["review_status"],
                "ai_b_reviewer": second["reviewer"],
                "ai_b_reviewed_at": second["reviewed_at"],
                "ai_b_notes": second["notes"],
                "disagreement_fields": "risk_label_review",
                "final_risk_label": "",
                "adjudication_status": "pending_project_owner",
                "adjudicator_id": "",
                "adjudicated_at": "",
                "rationale": "",
            }
        )
    return output


def _merge_alignment(
    left_rows: list[dict[str, str]],
    right_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    left, right = ({row["audit_id"]: row for row in rows} for rows in (left_rows, right_rows))
    if set(left) != set(right):
        raise ValueError("AI Alignment sheets have different audit_id sets")
    output: list[dict[str, str]] = []
    for audit_id in sorted(left):
        first, second = left[audit_id], right[audit_id]
        if any(first[field] != second[field] for field in ALIGNMENT_IMMUTABLE_FIELDS):
            raise ValueError(f"immutable Alignment content differs for audit_id={audit_id}")
        disagreements = []
        if first["task_alignment_label_review"] != second["task_alignment_label_review"]:
            disagreements.append("task_alignment_label_review")
        if first["action_realism_review"] != second["action_realism_review"]:
            disagreements.append("action_realism_review")
        if not disagreements:
            continue
        output.append(
            {
                **{field: first[field] for field in ALIGNMENT_IMMUTABLE_FIELDS},
                "ai_a_task_alignment_label": first["task_alignment_label_review"],
                "ai_a_action_realism": first["action_realism_review"],
                "ai_a_status": first["review_status"],
                "ai_a_reviewer": first["reviewer"],
                "ai_a_reviewed_at": first["reviewed_at"],
                "ai_a_notes": first["notes"],
                "ai_b_task_alignment_label": second["task_alignment_label_review"],
                "ai_b_action_realism": second["action_realism_review"],
                "ai_b_status": second["review_status"],
                "ai_b_reviewer": second["reviewer"],
                "ai_b_reviewed_at": second["reviewed_at"],
                "ai_b_notes": second["notes"],
                "disagreement_fields": ";".join(disagreements),
                "final_task_alignment_label": "",
                "final_action_realism": "",
                "adjudication_status": "pending_project_owner",
                "adjudicator_id": "",
                "adjudicated_at": "",
                "rationale": "",
            }
        )
    return output


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def build_package(
    *,
    reviewer_a_risk: str | Path,
    reviewer_b_risk: str | Path,
    reviewer_a_alignment: str | Path,
    reviewer_b_alignment: str | Path,
    audit_manifest: str | Path,
    ai_review_manifest: str | Path,
    ai_review_analysis: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    paths = {
        "ai_a_risk": Path(reviewer_a_risk),
        "ai_b_risk": Path(reviewer_b_risk),
        "ai_a_alignment": Path(reviewer_a_alignment),
        "ai_b_alignment": Path(reviewer_b_alignment),
    }
    audit_manifest_path = Path(audit_manifest)
    ai_manifest_path = Path(ai_review_manifest)
    analysis_path = Path(ai_review_analysis)
    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite adjudication package: {destination}")
    if not all(path.is_file() for path in (*paths.values(), audit_manifest_path, ai_manifest_path, analysis_path)):
        raise FileNotFoundError("all AI sheets, manifests and analysis must exist")

    risk_a = _read_csv(paths["ai_a_risk"], RISK_FIELDS)
    risk_b = _read_csv(paths["ai_b_risk"], RISK_FIELDS)
    alignment_a = _read_csv(paths["ai_a_alignment"], ALIGNMENT_FIELDS)
    alignment_b = _read_csv(paths["ai_b_alignment"], ALIGNMENT_FIELDS)
    reviewer_ids = {
        "ai_a": _reviewer_id(risk_a, paths["ai_a_risk"]),
        "ai_b": _reviewer_id(risk_b, paths["ai_b_risk"]),
    }
    if reviewer_ids["ai_a"] == reviewer_ids["ai_b"]:
        raise ValueError("AI reviewers must have distinct IDs")
    for slot, rows, path in (
        ("ai_a", alignment_a, paths["ai_a_alignment"]),
        ("ai_b", alignment_b, paths["ai_b_alignment"]),
    ):
        if _reviewer_id(rows, path) != reviewer_ids[slot]:
            raise ValueError("Risk and Alignment reviewer IDs must match per AI")
    _validate_ai_source_values(
        risk_a=risk_a,
        risk_b=risk_b,
        alignment_a=alignment_a,
        alignment_b=alignment_b,
        reviewer_ids=reviewer_ids,
    )
    ai_manifest = _assert_ai_manifest_binding(
        ai_manifest_path,
        audit_manifest_path=audit_manifest_path,
        paths=paths,
    )
    analysis = _read_json(analysis_path)
    audit_manifest = _validate_audit_manifest(
        audit_manifest_path,
        expected_risk_rows=len(risk_a),
        expected_alignment_rows=len(alignment_a),
    )
    _assert_provenance_bundle(
        audit_manifest_path=audit_manifest_path,
        ai_manifest_path=ai_manifest_path,
        analysis_path=analysis_path,
        audit_manifest=audit_manifest,
        ai_manifest=ai_manifest,
        analysis=analysis,
        reviewer_ids=reviewer_ids,
        risk_rows=len(risk_a),
        alignment_rows=len(alignment_a),
    )

    risk_rows = _merge_risk(risk_a, risk_b)
    alignment_rows = _merge_alignment(alignment_a, alignment_b)
    if not risk_rows and not alignment_rows:
        raise ValueError("no AI disagreements found; no package created")

    destination.mkdir(parents=True)
    risk_path = destination / "risk_disagreement_adjudication.csv"
    alignment_path = destination / "alignment_disagreement_adjudication.csv"
    _write_csv(risk_path, RISK_OUTPUT_FIELDS, risk_rows)
    _write_csv(alignment_path, ALIGNMENT_OUTPUT_FIELDS, alignment_rows)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "status": PACKAGE_STATUS,
        "evidence_status": AI_EVIDENCE_STATUS,
        "review_mode": "dual_ai_engineering_with_project_owner_adjudication",
        "protocol_version": ai_manifest.get("protocol_version"),
        "ai_reviewer_ids": reviewer_ids,
        "human_verified": False,
        "formal_training_authorized": False,
        "constraints": {
            "source_reviews_preserved": True,
            "sealed_seed_labels_included": False,
            "human_v2_blind_package_modified": False,
            "this_package_satisfies_independent_human_blind_gate": False,
            "independent_human_blind_gate_satisfied": False,
            "training_authorization_granted": False,
            "codex_must_not_fill_final_fields": True,
        },
        "source_evidence": {
            "audit_manifest": _source_binding(audit_manifest_path),
            "ai_review_manifest": _source_binding(ai_manifest_path),
            "ai_review_analysis": _source_binding(analysis_path),
            "reviewer_a_risk": _source_binding(paths["ai_a_risk"]),
            "reviewer_b_risk": _source_binding(paths["ai_b_risk"]),
            "reviewer_a_alignment": _source_binding(paths["ai_a_alignment"]),
            "reviewer_b_alignment": _source_binding(paths["ai_b_alignment"]),
        },
        "source_analysis_status": analysis.get("status"),
        "sheets": {
            risk_path.name: {"rows": len(risk_rows), "build_sha256": file_sha256(risk_path)},
            alignment_path.name: {
                "rows": len(alignment_rows),
                "build_sha256": file_sha256(alignment_path),
            },
        },
        "disagreement_counts": {
            "risk": len(risk_rows),
            "alignment": len(alignment_rows),
            "total": len(risk_rows) + len(alignment_rows),
        },
    }
    canonical = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    manifest["sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    manifest_path = destination / "adjudication_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (destination / "README.md").write_text(
        "\n".join(
            (
                "# Candidate 8 AI disagreement adjudication",
                "",
                "This is a supplementary project-owner review of disagreements from a dual-AI engineering run.",
                "It is not the independent human v2 blind package and does not satisfy that gate.",
                "It contains no sealed seed labels and must not overwrite the source AI sheets.",
                "",
                "Fill only the `final_*`, `adjudication_status`, `adjudicator_id`,",
                "`adjudicated_at` and `rationale` fields. Keep all immutable and AI opinion fields unchanged.",
                "Use exact protocol labels, a stable adjudicator ID, a timezone-aware ISO 8601 time,",
                "and a non-empty rationale for every row. This package must never set",
                "`human_verified=true` or `formal_training_authorized=true`.",
                "",
                "After the owner finishes, run the validator to create a non-overwriting submission receipt.",
                "",
            )
        ),
        encoding="utf-8",
    )
    return {"output_dir": str(destination.resolve()), "manifest": manifest}


def _validate_timestamp(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _package_source_paths(manifest: dict[str, Any]) -> dict[str, Path]:
    source = manifest.get("source_evidence")
    if not isinstance(source, dict) or set(source) != SOURCE_EVIDENCE_KEYS:
        raise ValueError("source evidence must bind all seven input files")
    paths: dict[str, Path] = {}
    for name, declaration in source.items():
        if not isinstance(declaration, dict):
            raise ValueError(f"source evidence is invalid for {name}")
        raw_path = declaration.get("path")
        path = Path(str(raw_path or "")).resolve()
        if not path.is_file():
            raise ValueError(f"source evidence file is missing for {name}")
        claimed = _require_sha256(declaration.get("sha256"), f"source evidence {name} sha256")
        if claimed != file_sha256(path):
            raise ValueError(f"source evidence changed for {name}")
        paths[name] = path
    return paths


def _assert_package_manifest_contract(
    manifest: dict[str, Any],
    *,
    package: Path,
    risk_path: Path,
    alignment_path: Path,
    risk_rows: list[dict[str, str]],
    alignment_rows: list[dict[str, str]],
) -> None:
    claimed = _require_sha256(manifest.get("sha256"), "adjudication manifest sha256")
    if claimed != _canonical_sha256(manifest):
        raise ValueError("adjudication manifest self-hash mismatch")
    expected_flags = {
        "source_reviews_preserved": True,
        "sealed_seed_labels_included": False,
        "human_v2_blind_package_modified": False,
        "this_package_satisfies_independent_human_blind_gate": False,
        "independent_human_blind_gate_satisfied": False,
        "training_authorization_granted": False,
        "codex_must_not_fill_final_fields": True,
    }
    if manifest.get("schema_version") != 1 or manifest.get("status") != PACKAGE_STATUS:
        raise ValueError("adjudication manifest status or schema drifted")
    if manifest.get("evidence_status") != AI_EVIDENCE_STATUS:
        raise ValueError("adjudication manifest evidence status drifted")
    if manifest.get("review_mode") != "dual_ai_engineering_with_project_owner_adjudication":
        raise ValueError("adjudication manifest review mode drifted")
    if manifest.get("human_verified") is not False:
        raise ValueError("package provenance flags must remain false")
    if manifest.get("formal_training_authorized") is not False:
        raise ValueError("package provenance flags must remain false")
    if manifest.get("constraints") != expected_flags:
        raise ValueError("adjudication manifest constraints drifted")
    sheets = manifest.get("sheets")
    if not isinstance(sheets, dict) or set(sheets) != {risk_path.name, alignment_path.name}:
        raise ValueError("adjudication sheet declarations drifted")
    expected_rows = {
        risk_path.name: len(risk_rows),
        alignment_path.name: len(alignment_rows),
    }
    for name, declaration in sheets.items():
        if not isinstance(declaration, dict) or declaration.get("rows") != expected_rows[name]:
            raise ValueError("adjudication sheet row counts drifted")
        _require_sha256(declaration.get("build_sha256"), f"{name} build_sha256")
    counts = manifest.get("disagreement_counts")
    expected_counts = {
        "risk": len(risk_rows),
        "alignment": len(alignment_rows),
        "total": len(risk_rows) + len(alignment_rows),
    }
    if counts != expected_counts or not expected_counts["total"]:
        raise ValueError("adjudication disagreement counts drifted")
    unexpected = sorted(
        item.name
        for item in package.iterdir()
        if not item.is_file() or item.name not in PACKAGE_FILES
    )
    if unexpected:
        raise ValueError(f"unexpected files in adjudication package: {unexpected}")


def validate_package(package_dir: str | Path, receipt_path: str | Path | None = None) -> dict[str, Any]:
    package = Path(package_dir)
    if not package.is_dir():
        raise FileNotFoundError(f"adjudication package directory is missing: {package}")
    manifest = _read_json(package / "adjudication_manifest.json")
    source_paths = _package_source_paths(manifest)
    risk_a = _read_csv(source_paths["reviewer_a_risk"], RISK_FIELDS)
    risk_b = _read_csv(source_paths["reviewer_b_risk"], RISK_FIELDS)
    alignment_a = _read_csv(source_paths["reviewer_a_alignment"], ALIGNMENT_FIELDS)
    alignment_b = _read_csv(source_paths["reviewer_b_alignment"], ALIGNMENT_FIELDS)
    reviewer_ids = {
        "ai_a": _reviewer_id(risk_a, source_paths["reviewer_a_risk"]),
        "ai_b": _reviewer_id(risk_b, source_paths["reviewer_b_risk"]),
    }
    if reviewer_ids["ai_a"] == reviewer_ids["ai_b"]:
        raise ValueError("AI reviewers must have distinct IDs")
    for slot, rows, path in (
        ("ai_a", alignment_a, source_paths["reviewer_a_alignment"]),
        ("ai_b", alignment_b, source_paths["reviewer_b_alignment"]),
    ):
        if _reviewer_id(rows, path) != reviewer_ids[slot]:
            raise ValueError("Risk and Alignment reviewer IDs must match per AI")
    _validate_ai_source_values(
        risk_a=risk_a,
        risk_b=risk_b,
        alignment_a=alignment_a,
        alignment_b=alignment_b,
        reviewer_ids=reviewer_ids,
    )
    ai_manifest = _assert_ai_manifest_binding(
        source_paths["ai_review_manifest"],
        audit_manifest_path=source_paths["audit_manifest"],
        paths={
            "ai_a_risk": source_paths["reviewer_a_risk"],
            "ai_b_risk": source_paths["reviewer_b_risk"],
            "ai_a_alignment": source_paths["reviewer_a_alignment"],
            "ai_b_alignment": source_paths["reviewer_b_alignment"],
        },
    )
    audit_manifest = _validate_audit_manifest(
        source_paths["audit_manifest"],
        expected_risk_rows=len(risk_a),
        expected_alignment_rows=len(alignment_a),
    )
    analysis = _read_json(source_paths["ai_review_analysis"])
    _assert_provenance_bundle(
        audit_manifest_path=source_paths["audit_manifest"],
        ai_manifest_path=source_paths["ai_review_manifest"],
        analysis_path=source_paths["ai_review_analysis"],
        audit_manifest=audit_manifest,
        ai_manifest=ai_manifest,
        analysis=analysis,
        reviewer_ids=reviewer_ids,
        risk_rows=len(risk_a),
        alignment_rows=len(alignment_a),
    )
    if manifest.get("protocol_version") != ai_manifest.get("protocol_version"):
        raise ValueError("adjudication manifest protocol_version drifted")
    if manifest.get("ai_reviewer_ids") != reviewer_ids:
        raise ValueError("adjudication manifest reviewer IDs drifted")
    if manifest.get("source_analysis_status") != analysis.get("status"):
        raise ValueError("adjudication manifest analysis status drifted")
    expected_risk = _merge_risk(
        risk_a,
        risk_b,
    )
    expected_alignment = _merge_alignment(
        alignment_a,
        alignment_b,
    )
    risk_path = package / "risk_disagreement_adjudication.csv"
    alignment_path = package / "alignment_disagreement_adjudication.csv"
    risk_rows = _read_csv(risk_path, RISK_OUTPUT_FIELDS, allow_empty=True)
    alignment_rows = _read_csv(alignment_path, ALIGNMENT_OUTPUT_FIELDS, allow_empty=True)
    _assert_package_manifest_contract(
        manifest,
        package=package,
        risk_path=risk_path,
        alignment_path=alignment_path,
        risk_rows=risk_rows,
        alignment_rows=alignment_rows,
    )
    errors: list[str] = []
    for current, expected, fields, name in (
        (risk_rows, expected_risk, RISK_OUTPUT_FIELDS[:-5], "Risk"),
        (alignment_rows, expected_alignment, ALIGNMENT_OUTPUT_FIELDS[:-6], "Alignment"),
    ):
        if len(current) != len(expected):
            errors.append(f"{name} row count changed")
            continue
        for index, (actual, baseline) in enumerate(zip(current, expected, strict=True)):
            if any(actual[field] != baseline[field] for field in fields):
                errors.append(f"{name} immutable/AI fields changed at row {index + 1}")
    adjudicators: set[str] = set()
    for row in risk_rows:
        if row["final_risk_label"] not in RISK_LABELS:
            errors.append(f"invalid final Risk label for {row['audit_id']}")
        adjudicators.add(row["adjudicator_id"].strip())
        if row["adjudication_status"] != "completed_project_owner":
            errors.append(f"Risk adjudication is incomplete for {row['audit_id']}")
        if not row["rationale"].strip() or not _validate_timestamp(row["adjudicated_at"]):
            errors.append(f"Risk provenance/rationale is incomplete for {row['audit_id']}")
    for row in alignment_rows:
        if row["final_task_alignment_label"] not in ALIGNMENT_LABELS:
            errors.append(f"invalid final Alignment label for {row['audit_id']}")
        if row["final_action_realism"] not in REALISM_LABELS:
            errors.append(f"invalid final action realism for {row['audit_id']}")
        adjudicators.add(row["adjudicator_id"].strip())
        if row["adjudication_status"] != "completed_project_owner":
            errors.append(f"Alignment adjudication is incomplete for {row['audit_id']}")
        if not row["rationale"].strip() or not _validate_timestamp(row["adjudicated_at"]):
            errors.append(f"Alignment provenance/rationale is incomplete for {row['audit_id']}")
    if not adjudicators or "" in adjudicators or len(adjudicators) != 1:
        errors.append("all rows must use one stable non-empty adjudicator_id")
    if errors:
        raise ValueError("; ".join(errors))

    receipt = {
        "schema_version": 1,
        "status": "project_owner_ai_disagreement_adjudication_complete",
        "human_verified": False,
        "formal_training_authorized": False,
        "package_manifest_sha256": file_sha256(package / "adjudication_manifest.json"),
        "package_manifest_canonical_sha256": manifest["sha256"],
        "sheets": {
            risk_path.name: {"rows": len(risk_rows), "sha256": file_sha256(risk_path)},
            alignment_path.name: {
                "rows": len(alignment_rows),
                "sha256": file_sha256(alignment_path),
            },
        },
        "disagreement_counts": manifest["disagreement_counts"],
        "constraints": {
            "independent_human_blind_gate_satisfied": False,
            "training_authorization_granted": False,
            "human_verified": False,
            "formal_training_authorized": False,
        },
        "source_evidence": manifest["source_evidence"],
        "adjudicator_id": next(iter(adjudicators)),
        "note": "This receipt does not satisfy the independent human v2 blind-review gate.",
    }
    destination = Path(receipt_path) if receipt_path is not None else package / "submission_receipt.json"
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite receipt: {destination}")
    destination.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"receipt_path": str(destination.resolve()), "receipt": receipt}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--reviewer-a-risk", type=Path, required=True)
    build.add_argument("--reviewer-b-risk", type=Path, required=True)
    build.add_argument("--reviewer-a-alignment", type=Path, required=True)
    build.add_argument("--reviewer-b-alignment", type=Path, required=True)
    build.add_argument("--audit-manifest", type=Path, required=True)
    build.add_argument("--ai-review-manifest", type=Path, required=True)
    build.add_argument("--ai-review-analysis", type=Path, required=True)
    build.add_argument("--output-dir", type=Path, required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--package-dir", type=Path, required=True)
    validate.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    if args.command == "build":
        result = build_package(
            reviewer_a_risk=args.reviewer_a_risk,
            reviewer_b_risk=args.reviewer_b_risk,
            reviewer_a_alignment=args.reviewer_a_alignment,
            reviewer_b_alignment=args.reviewer_b_alignment,
            audit_manifest=args.audit_manifest,
            ai_review_manifest=args.ai_review_manifest,
            ai_review_analysis=args.ai_review_analysis,
            output_dir=args.output_dir,
        )
    else:
        result = validate_package(args.package_dir, args.receipt)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
