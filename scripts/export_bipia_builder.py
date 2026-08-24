from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DISTRIBUTIONS = {
    "PyYAML": "PyYAML",
    "jsonlines": "jsonlines",
    "nltk": "nltk",
    "numpy": "numpy",
    "pandas": "pandas",
    "transformers": "transformers",
}


def _expected_revision() -> str:
    with (ROOT / "configs" / "upstream_sources.yaml").open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)["sources"]["bipia"]["revision"]


def _head(path: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _worktree_status(path: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(path), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _jsonl_rows(path: Path) -> int:
    rows = 0
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}") from exc
            rows += 1
    return rows


def _output_evidence(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Builder output is not a file: {path}")
    return {
        "path": str(path.resolve()),
        "rows": _jsonl_rows(path),
        "sha256": _sha256(path),
    }


def _load_source_manifest(path: Path) -> tuple[dict[str, Any], str]:
    if not path.is_file():
        raise FileNotFoundError(f"Source manifest is not a file: {path}")
    manifest_sha256 = _sha256(path)
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Source manifest is not valid JSON: {path}") from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != 1
        or not isinstance(manifest.get("sources"), list)
    ):
        raise ValueError(f"Source manifest has an invalid schema: {path}")
    return manifest, manifest_sha256


def _manifest_input_evidence(
    *,
    label: str,
    path: Path,
    bipia_root: Path,
    manifest_files: list[Any],
) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"{label} input is not a file: {resolved}")
    try:
        relative = resolved.relative_to(bipia_root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"{label} input is outside the pinned BIPIA root: {resolved}") from exc
    matches = [
        item
        for item in manifest_files
        if isinstance(item, dict) and item.get("path") == relative
    ]
    if len(matches) != 1:
        raise ValueError(
            f"{label} input must have exactly one source-manifest entry: {relative}"
        )
    entry = matches[0]
    expected_size = entry.get("size")
    expected_sha256 = entry.get("sha256")
    if type(expected_size) is not int or not isinstance(expected_sha256, str):
        raise ValueError(f"{label} source-manifest evidence is malformed: {relative}")
    actual_size = resolved.stat().st_size
    actual_sha256 = _sha256(resolved)
    if actual_size != expected_size or actual_sha256 != expected_sha256:
        raise RuntimeError(
            f"{label} input does not match source manifest: {relative} "
            f"(size {actual_size} != {expected_size} or sha256 mismatch)"
        )
    return {"path": str(resolved), "size": actual_size, "sha256": actual_sha256}


def _verify_source_binding(
    *,
    source_manifest: Path,
    bipia_root: Path,
    contexts: Path,
    attacks: Path,
    expected_revision: str,
    actual_revision: str,
) -> dict[str, dict[str, Any]]:
    if actual_revision != expected_revision:
        raise RuntimeError(
            f"BIPIA revision mismatch: expected {expected_revision}, got {actual_revision}"
        )
    if _worktree_status(bipia_root):
        raise RuntimeError("BIPIA worktree has local changes at the pinned revision")
    manifest, manifest_sha256 = _load_source_manifest(source_manifest)
    bipia_entries = [
        item
        for item in manifest["sources"]
        if isinstance(item, dict) and item.get("name") == "bipia"
    ]
    if len(bipia_entries) != 1:
        raise ValueError("Source manifest must contain exactly one BIPIA entry")
    bipia_entry = bipia_entries[0]
    if bipia_entry.get("revision") != expected_revision:
        raise RuntimeError(
            "BIPIA source-manifest revision does not match the frozen expected revision"
        )
    manifest_target = bipia_entry.get("target")
    if not isinstance(manifest_target, str):
        raise ValueError("BIPIA source-manifest target is missing")
    if Path(manifest_target).resolve() != bipia_root.resolve():
        raise RuntimeError("BIPIA root does not match the source-manifest target")
    manifest_files = bipia_entry.get("files")
    if not isinstance(manifest_files, list):
        raise ValueError("BIPIA source-manifest files are missing")
    return {
        "source_manifest": {
            "path": str(source_manifest.resolve()),
            "file_sha256": manifest_sha256,
        },
        "contexts": _manifest_input_evidence(
            label="contexts",
            path=contexts,
            bipia_root=bipia_root,
            manifest_files=manifest_files,
        ),
        "attacks": _manifest_input_evidence(
            label="attacks",
            path=attacks,
            bipia_root=bipia_root,
            manifest_files=manifest_files,
        ),
    }


def _assert_source_binding_unchanged(
    *,
    binding: dict[str, dict[str, Any]],
    bipia_root: Path,
    expected_revision: str,
) -> None:
    if _head(bipia_root) != expected_revision:
        raise RuntimeError("BIPIA revision changed while the builder was running")
    if _worktree_status(bipia_root):
        raise RuntimeError("BIPIA worktree changed while the builder was running")
    manifest = binding["source_manifest"]
    if _sha256(Path(manifest["path"])) != manifest["file_sha256"]:
        raise RuntimeError("Source manifest changed while the builder was running")
    for label in ("contexts", "attacks"):
        evidence = binding[label]
        path = Path(evidence["path"])
        if path.stat().st_size != evidence["size"] or _sha256(path) != evidence["sha256"]:
            raise RuntimeError(f"{label} input changed while the builder was running")


def _environment_evidence() -> dict[str, Any]:
    packages: dict[str, str] = {}
    for label, distribution in PACKAGE_DISTRIBUTIONS.items():
        try:
            packages[label] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            packages[label] = "not-installed"
    return {"python": platform.python_version(), "packages": dict(sorted(packages.items()))}


def _run_builder(
    *,
    bipia_root: Path,
    task: str,
    contexts: Path,
    attacks: Path,
    output: Path,
    seed: int,
) -> int:
    previous_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(bipia_root.resolve()))
    try:
        from bipia.data import AutoPIABuilder

        builder = AutoPIABuilder.from_name(task)(seed=seed)
        frame = builder(str(contexts), str(attacks))
        frame.to_json(output, orient="records", lines=True, force_ascii=False)
        return len(frame)
    finally:
        sys.path.pop(0)
        sys.dont_write_bytecode = previous_dont_write_bytecode


@contextmanager
def _temporary_path(parent: Path, name: str) -> Iterator[Path]:
    parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_path = tempfile.mkstemp(prefix=f".{name}.", suffix=".tmp", dir=parent)
    os.close(descriptor)
    path = Path(raw_path)
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


def _publish_without_overwrite(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, target)
    except FileExistsError as exc:
        raise FileExistsError(f"Refusing to overwrite {target}") from exc
    source.unlink()


def _write_report_atomic(path: Path, report: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite builder report: {path}")
    with _temporary_path(path.parent, path.name) as temporary:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(report, handle, indent=2, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        _publish_without_overwrite(temporary, path)


def _build_report(
    *,
    status: str,
    task: str,
    seed: int,
    expected_revision: str,
    actual_revision: str,
    binding: dict[str, dict[str, Any]],
    output: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": status,
        "execution_owner": "project_owner",
        "task": task,
        "seed": seed,
        "expected_revision": expected_revision,
        "actual_revision": actual_revision,
        "source_manifest": binding["source_manifest"],
        "contexts": binding["contexts"],
        "attacks": binding["attacks"],
        "output": output,
        "environment": _environment_evidence(),
    }


def _build_temporary_output(
    *,
    bipia_root: Path,
    task: str,
    contexts: Path,
    attacks: Path,
    output: Path,
    seed: int,
) -> dict[str, Any]:
    builder_rows = _run_builder(
        bipia_root=bipia_root,
        task=task,
        contexts=contexts,
        attacks=attacks,
        output=output,
        seed=seed,
    )
    evidence = _output_evidence(output)
    if builder_rows != evidence["rows"]:
        raise RuntimeError(
            f"Builder row count does not match JSONL rows: {builder_rows} != {evidence['rows']}"
        )
    return evidence


def _execute(args: argparse.Namespace, report_path: Path) -> dict[str, Any]:
    if args.output.exists() or report_path.exists():
        existing = [path for path in (args.output, report_path) if path.exists()]
        raise FileExistsError(
            "Refusing to overwrite builder output or report: "
            + ", ".join(str(path) for path in existing)
        )
    expected_revision = _expected_revision()
    actual_revision = _head(args.bipia_root)
    binding = _verify_source_binding(
        source_manifest=args.source_manifest,
        bipia_root=args.bipia_root,
        contexts=args.contexts,
        attacks=args.attacks,
        expected_revision=expected_revision,
        actual_revision=actual_revision,
    )
    with _temporary_path(args.output.parent, args.output.name) as temporary:
        temporary_evidence = _build_temporary_output(
            bipia_root=args.bipia_root,
            task=args.task,
            contexts=args.contexts,
            attacks=args.attacks,
            output=temporary,
            seed=args.seed,
        )
        _assert_source_binding_unchanged(
            binding=binding,
            bipia_root=args.bipia_root,
            expected_revision=expected_revision,
        )
        _publish_without_overwrite(temporary, args.output)
    output_evidence = {**temporary_evidence, "path": str(args.output.resolve())}
    report = _build_report(
        status="generated_verified",
        task=args.task,
        seed=args.seed,
        expected_revision=expected_revision,
        actual_revision=actual_revision,
        binding=binding,
        output=output_evidence,
    )
    _write_report_atomic(report_path, report)
    return report


def _verify_existing(args: argparse.Namespace, report_path: Path) -> dict[str, Any]:
    if report_path.exists():
        raise FileExistsError(f"Refusing to overwrite builder report: {report_path}")
    if not args.output.is_file():
        raise FileNotFoundError(f"Existing builder output is not a file: {args.output}")
    expected_revision = _expected_revision()
    actual_revision = _head(args.bipia_root)
    binding = _verify_source_binding(
        source_manifest=args.source_manifest,
        bipia_root=args.bipia_root,
        contexts=args.contexts,
        attacks=args.attacks,
        expected_revision=expected_revision,
        actual_revision=actual_revision,
    )
    existing_evidence = _output_evidence(args.output)
    with _temporary_path(args.output.parent, args.output.name) as temporary:
        reproduction = _build_temporary_output(
            bipia_root=args.bipia_root,
            task=args.task,
            contexts=args.contexts,
            attacks=args.attacks,
            output=temporary,
            seed=args.seed,
        )
        _assert_source_binding_unchanged(
            binding=binding,
            bipia_root=args.bipia_root,
            expected_revision=expected_revision,
        )
        current_evidence = _output_evidence(args.output)
        if current_evidence != existing_evidence:
            raise RuntimeError("Existing builder output changed during verification")
        if (
            reproduction["sha256"] != existing_evidence["sha256"]
            or reproduction["rows"] != existing_evidence["rows"]
        ):
            raise ValueError(
                "Existing builder output reproduction mismatch: "
                f"rows {existing_evidence['rows']} != {reproduction['rows']} or sha256 mismatch"
            )
    report = _build_report(
        status="reproduced_verified",
        task=args.task,
        seed=args.seed,
        expected_revision=expected_revision,
        actual_revision=actual_revision,
        binding=binding,
        output=existing_evidence,
    )
    report["reproduction"] = {
        "rows": reproduction["rows"],
        "sha256": reproduction["sha256"],
    }
    _write_report_atomic(report_path, report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Project-owner wrapper around the pinned official BIPIA builder"
    )
    parser.add_argument("--bipia-root", type=Path, required=True)
    parser.add_argument(
        "--task", choices=("code", "email", "qa", "abstract", "table"), required=True
    )
    parser.add_argument("--contexts", type=Path, required=True)
    parser.add_argument("--attacks", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--source-manifest", type=Path)
    parser.add_argument("--seed", type=int, default=42)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--execute",
        action="store_true",
        help="Generate the export. This data-processing flag is reserved for the project owner.",
    )
    modes.add_argument(
        "--verify-existing",
        action="store_true",
        help=(
            "Rebuild and verify an existing export without modifying it. "
            "This flag is reserved for the project owner."
        ),
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    report_path = args.report or args.output.with_suffix(".builder.json")
    mode = "execute" if args.execute else "verify_existing" if args.verify_existing else "preview_only"
    plan = {
        "mode": mode,
        "bipia_root": str(args.bipia_root.resolve()),
        "expected_revision": _expected_revision(),
        "task": args.task,
        "contexts": str(args.contexts.resolve()),
        "attacks": str(args.attacks.resolve()),
        "output": str(args.output.resolve()),
        "report": str(report_path.resolve()),
        "source_manifest": (
            str(args.source_manifest.resolve()) if args.source_manifest is not None else None
        ),
        "seed": args.seed,
    }
    if mode == "preview_only":
        print(json.dumps(plan, indent=2))
        return
    if args.source_manifest is None:
        parser.error("--execute and --verify-existing require --source-manifest")
    if report_path.resolve() == args.output.resolve():
        parser.error("--report must differ from --output")
    report = (
        _execute(args, report_path) if args.execute else _verify_existing(args, report_path)
    )
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
