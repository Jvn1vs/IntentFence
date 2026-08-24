from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "configs" / "upstream_sources.yaml"
C1_SOURCES = ("bipia", "injecagent", "notinject", "agentdojo")


def load_source_specs(registry_path: Path = DEFAULT_REGISTRY) -> dict[str, dict[str, Any]]:
    with registry_path.open(encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    sources = payload.get("sources", {}) if isinstance(payload, dict) else {}
    return {name: sources[name] for name in C1_SOURCES if name in sources}


def build_plan(
    names: list[str], destination: Path, registry_path: Path = DEFAULT_REGISTRY
) -> list[dict[str, Any]]:
    specs = load_source_specs(registry_path)
    plan: list[dict[str, Any]] = []
    for name in names:
        if name not in specs:
            raise ValueError(f"Source {name!r} is not pinned in {registry_path}")
        spec = specs[name]
        method = "huggingface_snapshot" if spec["kind"] == "huggingface_dataset" else "git"
        plan.append(
            {
                "name": name,
                "method": method,
                "official_url": spec["official_url"],
                "revision": spec["revision"],
                "license_finding": spec["license"],
                "target": str((destination / name).resolve()),
            }
        )
    return plan


def _run_git_download(item: dict[str, Any], target: Path) -> None:
    target.mkdir(parents=True)
    subprocess.run(["git", "-C", str(target), "init"], check=True)
    subprocess.run(
        ["git", "-C", str(target), "remote", "add", "origin", item["official_url"]],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(target), "fetch", "--depth", "1", "origin", item["revision"]],
        check=True,
    )
    subprocess.run(["git", "-C", str(target), "checkout", "--detach", "FETCH_HEAD"], check=True)
    head = subprocess.run(
        ["git", "-C", str(target), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if head != item["revision"]:
        raise RuntimeError(f"Revision mismatch for {item['name']}: {head}")


def _run_huggingface_download(item: dict[str, Any], target: Path) -> None:
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError(
            "Install intentfence[data] before downloading Hugging Face data"
        ) from exc
    marker = "/datasets/"
    if marker not in item["official_url"]:
        raise ValueError(f"Cannot derive Hugging Face dataset id from {item['official_url']}")
    repo_id = item["official_url"].split(marker, maxsplit=1)[1].strip("/")
    snapshot_download(
        repo_id=repo_id,
        repo_type="dataset",
        revision=item["revision"],
        local_dir=target,
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_files(target: Path) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for path in sorted(target.rglob("*")):
        if (
            not path.is_file()
            or path.suffix in {".pyc", ".pyo"}
            or any(part in {".git", ".cache", "__pycache__"} for part in path.parts)
        ):
            continue
        files.append(
            {
                "path": path.relative_to(target).as_posix(),
                "size": path.stat().st_size,
                "sha256": _file_sha256(path),
            }
        )
    return files


def _git_output(target: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(target), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _validate_existing_git_source(item: dict[str, Any], target: Path) -> None:
    if not (target / ".git").is_dir():
        raise RuntimeError(
            f"Cannot resume {item['name']}: existing target is not a Git repository: {target}"
        )
    head = _git_output(target, "rev-parse", "HEAD")
    if head != item["revision"]:
        raise RuntimeError(
            f"Cannot resume {item['name']}: expected revision {item['revision']}, found {head}"
        )
    status = _git_output(target, "status", "--porcelain")
    if status:
        raise RuntimeError(
            f"Cannot resume {item['name']}: existing Git worktree has local changes"
        )


def _load_existing_manifest(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("sources"), list):
        raise RuntimeError(f"Cannot resume from malformed source manifest: {path}")
    return {
        source["name"]: source
        for source in payload["sources"]
        if isinstance(source, dict) and isinstance(source.get("name"), str)
    }


def _validate_existing_snapshot_source(
    item: dict[str, Any], target: Path, previous: dict[str, Any] | None
) -> None:
    if previous is None:
        raise RuntimeError(
            f"Cannot safely resume {item['name']}: existing snapshot has no completed manifest entry"
        )
    for key in ("method", "official_url", "revision"):
        if previous.get(key) != item[key]:
            raise RuntimeError(
                f"Cannot resume {item['name']}: existing manifest {key} does not match the plan"
            )
    expected_files = previous.get("files")
    if not isinstance(expected_files, list) or expected_files != _artifact_files(target):
        raise RuntimeError(
            f"Cannot resume {item['name']}: existing snapshot files do not match the manifest"
        )


def execute_plan(
    plan: list[dict[str, Any]], destination: Path, *, resume: bool = False
) -> dict[str, Any]:
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    manifest_path = destination / "source_manifest.json"
    previous_sources = _load_existing_manifest(manifest_path) if resume else {}
    completed: list[dict[str, Any]] = []
    for item in plan:
        target = Path(item["target"]).resolve()
        if target.parent != destination:
            raise ValueError(f"Unsafe target outside destination: {target}")
        if target.exists():
            if not resume:
                raise FileExistsError(f"Refusing to overwrite source directory: {target}")
            if item["method"] == "git":
                _validate_existing_git_source(item, target)
            else:
                _validate_existing_snapshot_source(
                    item, target, previous_sources.get(item["name"])
                )
            retrieval_status = "reused_verified"
        else:
            if item["method"] == "git":
                _run_git_download(item, target)
            else:
                _run_huggingface_download(item, target)
            retrieval_status = "downloaded"
        completed.append(
            {**item, "retrieval_status": retrieval_status, "files": _artifact_files(target)}
        )

    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "execution_owner": "project_owner",
        "sources": completed,
    }
    temporary_manifest = manifest_path.with_suffix(".json.tmp")
    temporary_manifest.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_manifest.replace(manifest_path)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preview or execute pinned source retrieval; preview is the safe default"
    )
    parser.add_argument("sources", nargs="+", choices=C1_SOURCES)
    parser.add_argument("--destination", type=Path, default=Path("data/raw"))
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually download. This flag is reserved for the project owner.",
    )
    parser.add_argument(
        "--acknowledge-source-terms",
        action="store_true",
        help="Confirm that the project owner reviewed source-specific licenses and terms.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Reuse existing sources only after validating their pinned revision and integrity; "
            "download missing sources and rebuild the complete manifest."
        ),
    )
    args = parser.parse_args()
    plan = build_plan(args.sources, args.destination, args.registry)
    if not args.execute:
        print(json.dumps({"mode": "preview_only", "plan": plan}, indent=2, ensure_ascii=False))
        return
    if not args.acknowledge_source_terms:
        parser.error("--execute requires --acknowledge-source-terms")
    print(
        json.dumps(
            execute_plan(plan, args.destination, resume=args.resume),
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
