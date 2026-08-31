from __future__ import annotations

import argparse
import json
import re
import subprocess
import tarfile
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import BinaryIO

REQUIRED_PUBLIC_DOCUMENTS = (
    "README.md",
    "LICENSE",
    "SECURITY.md",
    "docs/model_card.md",
    "docs/threat_model.md",
    "docs/reproducibility_checklist.md",
    "docs/ai_usage_disclosure.md",
    "docs/claim_evidence_matrix.md",
)
FORBIDDEN_ARTIFACT_DIRECTORIES = (
    "data/raw",
    "data/interim",
    "data/processed",
    "checkpoints",
    "artifacts",
    "runs",
    "wandb",
    "mlruns",
)
FORBIDDEN_WEIGHT_SUFFIXES = (
    ".onnx",
    ".pt",
    ".pth",
    ".safetensors",
    ".ckpt",
    ".bin",
    ".joblib",
    ".h5",
    ".hdf5",
    ".gguf",
    ".pb",
    ".tflite",
)
FORBIDDEN_DATA_SUFFIXES = (
    ".csv",
    ".tsv",
    ".parquet",
    ".arrow",
    ".feather",
    ".sqlite",
    ".db",
    ".pkl",
    ".pickle",
    ".npy",
    ".npz",
    ".zip",
    ".tar",
    ".gz",
    ".7z",
    ".jsonl",
)
FORBIDDEN_ARTIFACT_COMPONENTS = {
    "exports",
    "logs",
    "outputs",
    "predictions",
    "private",
    "results",
    "secrets",
}
PUBLIC_JSON_FILES = {
    "configs/protocol_lock.json",
    "configs/route_b_ai_review_manifest.example.json",
}
PUBLIC_SYNTHETIC_DATA_FILES = {"data/examples/smoke.jsonl"}
GENERATED_REPORT_DIRECTORIES = (
    "reports/tables",
    "reports/calibration",
    "reports/error_analysis",
    "reports/figures",
)
SECRET_PATTERNS = (
    re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(rb"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(rb"\b(?:ghp|github_pat|xoxb|xoxp|sk)-[A-Za-z0-9_-]{16,}\b"),
    re.compile(
        rb"(?i)\b(?:api[_ -]?key|secret|password|access[_ -]?token)\s*[:=]\s*"
        rb"[\"']?(?!<|YOUR_|CHANGE_ME|EXAMPLE|NONE|NULL)[A-Za-z0-9][A-Za-z0-9_./:+=-]{15,}"
    ),
)
SECRET_SCAN_CHUNK_BYTES = 64 * 1024
SECRET_SCAN_OVERLAP_BYTES = 512


@dataclass(frozen=True)
class ReleaseIssue:
    path: str
    category: str
    message: str


def _normalise(path: str | Path) -> str:
    normalised = str(path).replace("\\", "/")
    while normalised.startswith("./"):
        normalised = normalised[2:]
    return normalised


def _under(path: str, directory: str) -> bool:
    return path == directory or path.startswith(directory + "/")


def _git_paths(root: Path, *, include_untracked: bool) -> list[str] | None:
    if not (root / ".git").exists():
        return None
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=False,
        capture_output=True,
    )
    if tracked.returncode != 0:
        return None
    values = [value for value in tracked.stdout.decode("utf-8").split("\0") if value]
    if not include_untracked:
        return sorted(values)
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=False,
        capture_output=True,
    )
    if untracked.returncode == 0:
        values.extend(value for value in untracked.stdout.decode("utf-8").split("\0") if value)
    return sorted(set(values))


def _filesystem_paths(root: Path) -> list[str]:
    excluded = {".git", ".pytest_cache", ".ruff_cache", "__pycache__", "dist", "build"}
    return sorted(
        _normalise(item.relative_to(root))
        for item in root.rglob("*")
        if item.is_file() and not any(part in excluded for part in item.relative_to(root).parts)
    )


def _stream_contains_secret(handle: BinaryIO) -> bool:
    overlap = b""
    while chunk := handle.read(SECRET_SCAN_CHUNK_BYTES):
        payload = overlap + chunk
        if any(pattern.search(payload) for pattern in SECRET_PATTERNS):
            return True
        overlap = payload[-SECRET_SCAN_OVERLAP_BYTES:]
    return False


def _contains_secret(path: Path) -> bool:
    """Scan arbitrarily sized files, including binary files, for known secrets."""
    try:
        with path.open("rb") as handle:
            return _stream_contains_secret(handle)
    except OSError:
        return False


def _git_tree_paths(root: Path, ref: str) -> list[str]:
    result = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", "-z", ref],
        cwd=root,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"cannot inspect Git tree {ref}: {detail}")
    return sorted(
        _normalise(value)
        for value in result.stdout.decode("utf-8").split("\0")
        if value
    )


def _git_archive_secret_issues(root: Path, ref: str) -> list[ReleaseIssue]:
    process = subprocess.Popen(
        ["git", "archive", "--format=tar", ref],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    issues: list[ReleaseIssue] = []
    assert process.stdout is not None
    assert process.stderr is not None
    try:
        with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
            for member in archive:
                if not member.isfile():
                    continue
                handle = archive.extractfile(member)
                if handle is not None and _stream_contains_secret(handle):
                    issues.append(
                        ReleaseIssue(
                            _normalise(member.name),
                            "secret",
                            "high-confidence credential pattern detected",
                        )
                    )
    finally:
        process.stdout.close()
    error = process.stderr.read().decode("utf-8", errors="replace").strip()
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(f"cannot archive Git tree {ref}: {error}")
    return issues


def _path_issues(relative: str) -> list[ReleaseIssue]:
    path = _normalise(relative)
    lowered = path.casefold()
    name = Path(path).name.casefold()
    if name == ".gitkeep" or name == ".env.example":
        return []
    issues: list[ReleaseIssue] = []
    if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
        issues.append(ReleaseIssue(path, "credential", "environment files are not public artifacts"))
    components = {part.casefold() for part in path.split("/")[:-1]}
    if components & FORBIDDEN_ARTIFACT_COMPONENTS:
        issues.append(ReleaseIssue(path, "artifact", "private/output directories are forbidden"))
    if any(_under(lowered, directory) for directory in FORBIDDEN_ARTIFACT_DIRECTORIES):
        issues.append(ReleaseIssue(path, "artifact", "raw/model/runtime artifact directory is forbidden"))
    if Path(name).suffix.casefold() in FORBIDDEN_WEIGHT_SUFFIXES:
        issues.append(ReleaseIssue(path, "weight", "model weight/ONNX files must stay out of Git"))
    suffix = Path(name).suffix.casefold()
    if suffix in FORBIDDEN_DATA_SUFFIXES and lowered not in PUBLIC_SYNTHETIC_DATA_FILES:
        issues.append(ReleaseIssue(path, "data", "raw, serialized or generated data files are not public by default"))
    if suffix == ".json" and lowered not in PUBLIC_JSON_FILES:
        issues.append(ReleaseIssue(path, "data", "JSON files require an explicit public allowlist entry"))
    if any(_under(lowered, directory) for directory in GENERATED_REPORT_DIRECTORIES):
        issues.append(ReleaseIssue(path, "cache", "generated result/cache directory is not public by default"))
    if _under(lowered, "reports/data_quality") and Path(name).suffix.casefold() != ".md":
        issues.append(ReleaseIssue(path, "cache", "only public Markdown data-card files are allowed here"))
    return issues


def audit_public_release(
    root: str | Path,
    *,
    paths: Iterable[str | Path] | None = None,
    include_untracked: bool = False,
    require_documents: bool = True,
) -> list[ReleaseIssue]:
    """Return issues that would block a conservative public-source release."""

    repository = Path(root).resolve()
    if not repository.is_dir():
        raise FileNotFoundError(f"repository root does not exist: {repository}")
    if paths is not None:
        candidates = [_normalise(path) for path in paths]
    else:
        git_paths = _git_paths(repository, include_untracked=include_untracked)
        candidates = git_paths if git_paths is not None else _filesystem_paths(repository)
    issues = [issue for candidate in sorted(set(candidates)) for issue in _path_issues(candidate)]
    if require_documents:
        issues.extend(
            ReleaseIssue(path, "missing", "required public document is missing")
            for path in REQUIRED_PUBLIC_DOCUMENTS
            if not (repository / path).is_file()
        )
    for candidate in sorted(set(candidates)):
        path = repository / candidate
        if _contains_secret(path):
            issues.append(ReleaseIssue(candidate, "secret", "high-confidence credential pattern detected"))
    return sorted(set(issues), key=lambda issue: (issue.path, issue.category, issue.message))


def audit_public_release_git_tree(
    root: str | Path,
    ref: str = "HEAD",
    *,
    require_documents: bool = True,
) -> list[ReleaseIssue]:
    """Audit the exact committed Git tree that would be archived for a release."""
    repository = Path(root).resolve()
    if not repository.is_dir():
        raise FileNotFoundError(f"repository root does not exist: {repository}")
    candidates = _git_tree_paths(repository, ref)
    issues = [issue for candidate in candidates for issue in _path_issues(candidate)]
    if require_documents:
        candidate_set = set(candidates)
        issues.extend(
            ReleaseIssue(path, "missing", "required public document is missing")
            for path in REQUIRED_PUBLIC_DOCUMENTS
            if path not in candidate_set
        )
    issues.extend(_git_archive_secret_issues(repository, ref))
    return sorted(set(issues), key=lambda issue: (issue.path, issue.category, issue.message))


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the tracked source tree before public release")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--include-untracked",
        action="store_true",
        help="also audit non-ignored untracked files in the working tree",
    )
    parser.add_argument(
        "--git-tree",
        metavar="REF",
        help="audit the exact committed Git tree at REF instead of the working tree",
    )
    parser.add_argument("--json", action="store_true", help="print a machine-readable report")
    args = parser.parse_args()
    if args.git_tree and args.include_untracked:
        parser.error("--git-tree cannot be combined with --include-untracked")
    issues = (
        audit_public_release_git_tree(args.root, args.git_tree)
        if args.git_tree
        else audit_public_release(args.root, include_untracked=args.include_untracked)
    )
    report = {"status": "blocked" if issues else "passed", "issues": [asdict(issue) for issue in issues]}
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif issues:
        for issue in issues:
            print(f"{issue.category}: {issue.path}: {issue.message}")
    else:
        print("public release audit passed")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
