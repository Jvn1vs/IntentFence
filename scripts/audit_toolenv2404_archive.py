"""Inspect an already downloaded, approved ToolEnv archive; no network access."""
import hashlib
import json
from pathlib import Path

import yaml

from intentfence.toolenv_archive import inspect_archive

ROOT = Path(__file__).resolve().parents[1]


def main():
    config_path = ROOT / "configs/toolenv2404_attribution_audit_20260912.yaml"
    config_bytes = config_path.read_bytes()
    config = yaml.safe_load(config_bytes)
    if config["owner_approved_download_and_readonly_audit"] is not True:
        raise ValueError("source audit not approved")
    path = ROOT / "data/raw/toolenv2404/toolenv2404_filtered.tar.gz"
    data = path.read_bytes()
    if len(data) != config["expected_bytes"] or hashlib.sha256(data).hexdigest() != config["expected_sha256"]:
        raise ValueError("archive size or digest mismatch")
    result = inspect_archive(path, set(config["target_tool_names"]))
    result |= {"archive_sha256": hashlib.sha256(data).hexdigest(),
               "config_sha256": hashlib.sha256(config_bytes).hexdigest(),
               "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "reader_sha256": hashlib.sha256((ROOT / "src/intentfence/toolenv_archive.py").read_bytes()).hexdigest()}
    out = ROOT / "data/interim/toolenv2404_audit_20260912/metadata.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k:v for k,v in result.items() if k != "matches"}, indent=2))


if __name__ == "__main__":
    main()
