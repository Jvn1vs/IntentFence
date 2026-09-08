from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from verify_candidate_9 import verify  # noqa: E402


def test_completion_hash_detects_manifest_tampering(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    (tmp_path / ".complete").write_text("not-the-hash", encoding="utf-8")
    with pytest.raises(ValueError, match="completion hash"):
        verify(tmp_path, tmp_path)


def test_verifier_rejects_changed_output_even_with_valid_manifest_hash(tmp_path: Path) -> None:
    output = tmp_path / "train.jsonl"
    output.write_text("changed", encoding="utf-8")
    manifest = {
        "inputs": {},
        "implementation_sha256": {},
        "files": {
            "train": {"path": output.name, "sha256": hashlib.sha256(b"original").hexdigest()}
        },
    }
    payload = json.dumps(manifest).encode()
    (tmp_path / "manifest.json").write_bytes(payload)
    (tmp_path / ".complete").write_text(hashlib.sha256(payload).hexdigest(), encoding="utf-8")
    with pytest.raises(ValueError, match="Output hash mismatch"):
        verify(tmp_path, tmp_path)
