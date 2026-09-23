"""Bounded, read-only search for literal helper names inside ToolEnv JSON members."""

from __future__ import annotations

import hashlib
import tarfile
from pathlib import Path, PurePosixPath


def scan_helper_names(
    path: Path,
    targets: set[str],
    *,
    max_members: int = 100_000,
    max_uncompressed: int = 1_000_000_000,
    max_json: int = 20_000_000,
) -> dict:
    """Scan JSON bytes without extracting, parsing, or executing archive contents."""
    if not targets or any(not value or not value.isascii() for value in targets):
        raise ValueError("nonempty ASCII helper names required")
    if min(max_members, max_uncompressed, max_json) < 1:
        raise ValueError("positive archive limits required")
    needles = {name: name.encode("ascii") for name in targets}
    names: set[str] = set()
    hits: list[dict] = []
    total = json_files = 0
    with tarfile.open(path, mode="r|gz") as archive:
        for member in archive:
            if member.name in names:
                raise ValueError("duplicate archive member")
            names.add(member.name)
            total += member.size
            if len(names) > max_members or member.size < 0 or total > max_uncompressed:
                raise ValueError("archive inspection limit exceeded")
            pure = PurePosixPath(member.name)
            if pure.is_absolute() or ".." in pure.parts or "\\" in member.name:
                raise ValueError("unsafe archive member")
            if not pure.name.lower().endswith(".json"):
                continue
            if not member.isfile() or member.size > max_json:
                raise ValueError("invalid or oversized JSON member")
            handle = archive.extractfile(member)
            if handle is None:
                raise ValueError("unreadable JSON member")
            with handle:
                content = handle.read(max_json + 1)
            if len(content) != member.size:
                raise ValueError("JSON member length mismatch")
            json_files += 1
            found = sorted(name for name, needle in needles.items() if needle in content)
            if found:
                hits.append({
                    "member": member.name,
                    "bytes": member.size,
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "literal_names_found": found,
                })
    return {
        "members": len(names),
        "json_files_scanned": json_files,
        "declared_uncompressed_bytes": total,
        "targets": sorted(targets),
        "hits": hits,
        "scan_scope": "case-sensitive literal ASCII bytes in JSON members",
        "executed": False,
        "extracted_files": 0,
    }
