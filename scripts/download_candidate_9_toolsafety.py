"""Download the approved ToolSafety audit snapshot, never execute its contents."""

from __future__ import annotations

import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def download() -> None:
    approval_path = ROOT / "configs/candidate_9_toolsafety_audit.yaml"
    approval_bytes = approval_path.read_bytes()
    source = yaml.safe_load(approval_bytes)
    if source["owner_approved_download_and_readonly_audit"] is not True:
        raise ValueError("ToolSafety download and audit not approved")
    if (
        source["repository"] != "jinjinyien/ToolSafety"
        or source["revision"] != "7c444473e0dc0a822247858c249b10856ade04ef"
        or source["data_file"] != "toolsafety.json"
    ):
        raise ValueError("Source differs from approved snapshot")
    base = f"https://huggingface.co/datasets/{source['repository']}/resolve/{source['revision']}/"
    directory = ROOT / "data/raw/toolsafety"
    directory.mkdir(exist_ok=True)
    if any(directory.iterdir()):
        raise FileExistsError("Refusing to overwrite or reuse a nonempty ToolSafety directory")
    files = {}
    for name in ("README.md", "toolsafety.json"):
        maximum = 16_384 if name == "README.md" else source["expected_bytes"]
        partial = directory / (name + ".partial")
        hasher = hashlib.sha256()
        size = 0
        with urllib.request.urlopen(base + name, timeout=60) as response, partial.open("xb") as out:
            while block := response.read(1024 * 1024):
                size += len(block)
                if size > maximum:
                    raise ValueError("Source exceeds approved size envelope")
                out.write(block)
                hasher.update(block)
        if name == "toolsafety.json" and (
            size != source["expected_bytes"] or hasher.hexdigest() != source["expected_sha256"]
        ):
            raise ValueError("Pinned ToolSafety size/hash mismatch")
        if name == "README.md" and b"license: mit" not in partial.read_bytes():
            raise ValueError("Pinned card no longer declares MIT")
        partial.rename(directory / name)
        files[name] = {"size": size, "sha256": hasher.hexdigest(), "url": base + name}
        print(f"Downloaded and verified {name}: {size} bytes", flush=True)
    if approval_path.read_bytes() != approval_bytes:
        raise ValueError("Approval changed during download")
    manifest = {
        "source": source,
        "files": files,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "approval_file_sha256": hashlib.sha256(approval_bytes).hexdigest(),
        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "execution_owner": "codex",
        "status": "download_verified_for_readonly_audit_not_training_ready",
    }
    with (directory / "source_manifest.json").open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


if __name__ == "__main__":
    download()
