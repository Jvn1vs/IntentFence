"""Download only the owner-approved pinned Dolly source and record its hashes."""

from __future__ import annotations

import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def download() -> None:
    proposal = ROOT / "configs/candidate_9_source_proposals.yaml"
    source = yaml.safe_load(proposal.read_text(encoding="utf-8"))["sources"]["dolly_contexts"]
    if source["owner_approved"] is not True:
        raise ValueError("Dolly source terms are not approved")
    base = f"https://huggingface.co/datasets/{source['repository']}/resolve/{source['revision']}/"
    directory = ROOT / "data/raw/dolly"
    directory.mkdir(exist_ok=True)
    if any(directory.iterdir()):
        raise FileExistsError("Refusing to overwrite or silently reuse a nonempty Dolly directory")
    evidence = {}
    for name in ("README.md", source["data_file"]):
        with urllib.request.urlopen(base + name, timeout=60) as response:
            payload = response.read(20_000_001)
        if len(payload) > 20_000_000:
            raise ValueError("Download exceeds approved source size envelope")
        if name == source["data_file"] and len(payload) != source["expected_bytes"]:
            raise ValueError("Pinned data size mismatch")
        if name == "README.md" and b"license: cc-by-sa-3.0" not in payload:
            raise ValueError("Pinned license declaration changed")
        with (directory / name).open("xb") as handle:
            handle.write(payload)
        evidence[name] = {
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "url": base + name,
        }
        print(f"Downloaded and hashed {name}: {len(payload)} bytes", flush=True)
    manifest = {
        "source": source,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "execution_owner": "codex",
        "files": evidence,
        "approval_file_sha256": hashlib.sha256(proposal.read_bytes()).hexdigest(),
    }
    with (directory / "source_manifest.json").open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


if __name__ == "__main__":
    download()
