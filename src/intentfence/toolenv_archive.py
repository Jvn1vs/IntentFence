"""Read selected JSON metadata inside tar archives; never extract or execute."""
from __future__ import annotations

import hashlib
import json
import tarfile
from pathlib import Path, PurePosixPath


def inspect_archive(path: Path, targets: set[str], *, max_members: int = 100_000,
                    max_uncompressed: int = 1_000_000_000, max_json: int = 5_000_000) -> dict:
    if not targets or min(max_members, max_uncompressed, max_json) < 1:
        raise ValueError("nonempty targets and positive limits required")
    names, matches = set(), []
    total = 0
    with tarfile.open(path, mode="r|gz") as archive:
        for member in archive:
            if member.name in names:
                raise ValueError("duplicate member name")
            names.add(member.name)
            total += member.size
            if len(names) > max_members or member.size < 0 or total > max_uncompressed:
                raise ValueError("archive inspection limit exceeded")
            pure = PurePosixPath(member.name)
            matched = sorted(targets.intersection({pure.stem, *pure.parts[:-1]}))
            if not matched or pure.suffix.lower() != ".json":
                continue
            if not member.isfile() or pure.is_absolute() or ".." in pure.parts or "\\" in member.name:
                raise ValueError("unsafe or nonregular matching member")
            if member.size > max_json:
                raise ValueError("matching JSON exceeds limit")
            handle = archive.extractfile(member)
            if handle is None:
                raise ValueError("unreadable matching member")
            with handle:
                content = handle.read(max_json + 1)
            if len(content) != member.size:
                raise ValueError("member length mismatch")
            payload = json.loads(content)
            if not isinstance(payload, (dict, list)):
                raise ValueError("expected JSON object or list")
            matches.append({"member": member.name, "targets": matched, "bytes": len(content),
                            "sha256": hashlib.sha256(content).hexdigest(), "metadata": payload})
    return {"members": len(names), "declared_uncompressed_bytes": total, "matches": matches,
            "matched_targets": sorted({t for m in matches for t in m["targets"]}),
            "executed": False, "extracted_files": 0, "attribution_resolved": False}
