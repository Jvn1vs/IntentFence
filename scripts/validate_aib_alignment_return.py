"""Validate returned alignment forms without applying or promoting their labels."""
import argparse
import csv
import hashlib
import io
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from scripts.package_aib_alignment_review import FIELDS

ROOT = Path(__file__).resolve().parents[1]
FORM_HASHES = {"A": "5d4f967e2b95a44bc9fcb5721956073798748e65ea48b6135337125951d2f2ba",
               "B": "91fcfb905954ab850a92a9df2ac17d7dded4ed0e8bb596291b7fa978e2f0dd7a"}


def parse(data: bytes) -> list[dict]:
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline=""), strict=True)
    if reader.fieldnames != FIELDS:
        raise ValueError("unexpected CSV header")
    rows = list(reader)
    if not rows or any(None in r or any(v is None for v in r.values()) for r in rows):
        raise ValueError("empty form or malformed row")
    ids = [r["review_id"] for r in rows]
    if any(not value.strip() for value in ids) or len(set(ids)) != len(ids):
        raise ValueError("missing or duplicate review ID")
    return rows


def validate(template: bytes, returned: bytes, expected_reviewer: str) -> dict:
    if not expected_reviewer.strip():
        raise ValueError("reviewer identity required")
    original, completed = parse(template), parse(returned)
    if len(original) != len(completed):
        raise ValueError("row count changed")
    labels = Counter()
    for before, after in zip(original, completed, strict=True):
        if any(before[k] != after[k] for k in FIELDS[:6]):
            raise ValueError("immutable material or row order changed")
        if after["reviewer_id"] != expected_reviewer:
            raise ValueError("reviewer identity mismatch")
        stamp = datetime.fromisoformat(after["reviewed_at"])
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError("review timestamp requires timezone")
        status, label = after["review_status"], after["task_alignment_label_review"]
        if status == "completed":
            if label not in {"aligned", "unrelated", "ambiguous", "malicious"}:
                raise ValueError("invalid completed label")
        elif status == "unable_to_determine":
            if label or not after["notes"].strip():
                raise ValueError("abstention must have no label and a reason")
        else:
            raise ValueError("missing or invalid review status")
        if after["action_realism_review"] not in {"realistic", "unrealistic", "ambiguous"}:
            raise ValueError("invalid action realism")
        labels[label or "abstain"] += 1
    return {"rows": len(completed), "alignment_opinions": dict(labels),
            "form_integrity_verified": True, "reviewer_identity_authenticated": False,
            "independence_verified": False, "labels_applied": 0, "training_ready": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reviewer-slot", choices=["A", "B"], required=True)
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument("--returned", type=Path, required=True)
    args = parser.parse_args()
    template = (ROOT / f"data/interim/aib_alignment_review_20260912/reviewer_{args.reviewer_slot}/alignment.csv").read_bytes()
    if hashlib.sha256(template).hexdigest() != FORM_HASHES[args.reviewer_slot]:
        raise ValueError("original template changed")
    returned = args.returned.read_bytes()
    result = validate(template, returned, args.reviewer_id)
    result |= {"template_sha256": hashlib.sha256(template).hexdigest(),
               "returned_sha256": hashlib.sha256(returned).hexdigest(),
               "declared_reviewer_id": args.reviewer_id}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
