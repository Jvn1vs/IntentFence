"""Bind already-authored AI notes to prefixes; this does not perform AI review."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from verify_toolsafety_prefix_review import validate_reviews


def package_notes(package: Path) -> None:
    notes_bytes = (package / "ai_notes.json").read_bytes()
    full_bytes = (package / "ai_full_context_notes.json").read_bytes()
    notes, full = json.loads(notes_bytes), json.loads(full_bytes)
    prefixes = [json.loads(line) for line in (package / "prefixes.jsonl").read_bytes().splitlines()]
    if set(notes) != {str(i) for i in range(len(prefixes))} or not set(full) <= set(notes):
        raise ValueError("Authored notes do not cover package exactly")
    rows = []
    for i, prefix in enumerate(prefixes):
        rows.append({
            "review_id": prefix["review_id"], "prefix_sha256": prefix["prefix_sha256"],
            "reviewer": "AI/Codex", "review_date": "2026-09-11", "human_verified": False,
            "training_ready": False, "risk_label": None, "alignment_label": None,
            "focused_view_fields": ["user_goal", "untrusted_content", "proposed_action"],
            "focused_view_limitation": "Focused semantic first pass, not exhaustive history/tool-definition review. No attack proven is not a benign training label.",
            "view_redaction": "Some credential-like argument values hidden. Rows 60-79 additionally hid long tokens; function names were then re-read. Rows 83/98/99 affected by overbroad key matching were re-read.",
            "semantic_note": notes[str(i)], "full_context_pre_review": full.get(str(i)),
            "ai_notes_sha256": hashlib.sha256(notes_bytes).hexdigest(),
            "ai_full_context_notes_sha256": hashlib.sha256(full_bytes).hexdigest(),
            "independent_human_review": False, "labels_applied_to_training": False,
        })
    validate_reviews(prefixes, rows)
    with (package / "ai_pre_reviews.jsonl").open("x", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    package_notes(parser.parse_args().package)
