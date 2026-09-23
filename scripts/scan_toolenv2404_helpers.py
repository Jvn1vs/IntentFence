"""Verify the approved ToolEnv archive and scan for six ToolSafety helper names."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml

from intentfence.toolenv_helper_scan import scan_helper_names

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/toolenv2404_helper_scan_20260923.yaml"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    if config["owner_approved_readonly_audit"] is not True:
        raise ValueError("read-only archive audit not approved")
    path = ROOT / config["archive_path"]
    if path.stat().st_size != config["archive_bytes"] or sha(path) != config["archive_sha256"]:
        raise ValueError("approved archive bytes or hash mismatch")
    result = scan_helper_names(path, set(config["target_helper_names"]))
    result |= {
        "archive_sha256": config["archive_sha256"],
        "config_sha256": sha(CONFIG),
        "reader_sha256": sha(ROOT / "src/intentfence/toolenv_helper_scan.py"),
        "script_sha256": sha(Path(__file__)),
        "attribution_resolved": False,
        "training_ready": False,
    }
    out = ROOT / config["output_path"]
    allowed = (ROOT / "data/interim/toolenv2404_audit_20260912").resolve()
    if out.resolve().parent != allowed:
        raise ValueError("output outside approved interim directory")
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.verify:
        if out.read_bytes() != rendered.encode("utf-8"):
            raise ValueError("saved helper scan differs from replay")
    else:
        with out.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(rendered)
    print(json.dumps({
        "verified": args.verify,
        "members": result["members"],
        "json_files_scanned": result["json_files_scanned"],
        "hits": len(result["hits"]),
        "output_sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
    }))


if __name__ == "__main__":
    main()
