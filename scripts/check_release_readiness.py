"""Check the committed Git tree, local README links, and CI contract before release."""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import subprocess
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path

try:
    from .audit_public_release import (
        ReleaseIssue,
        _git_tree_paths,
        audit_public_release_git_tree,
    )
except ImportError:  # pragma: no cover - exercised when run as a script
    from audit_public_release import (  # type: ignore[no-redef]
        ReleaseIssue,
        _git_tree_paths,
        audit_public_release_git_tree,
    )

LOCAL_LINK_PATTERN = re.compile(r"\[[^\]]+\]\((<[^>]+>|[^)\s]+)")
REQUIRED_CI_COMMANDS = (
    "python -m pip install -e",
    "scripts/audit_public_release.py --include-untracked",
    "python -m ruff check .",
    "python -m pytest",
    "python -m compileall -q",
    "python -m pip check",
    "python -m build --wheel",
)


def _git_show(root: Path, ref: str, relative: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{ref}:{relative}"],
        cwd=root,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8")


def find_local_link_issues(
    markdown: str,
    tree_paths: Iterable[str],
    *,
    source_path: str = "README.md",
) -> list[ReleaseIssue]:
    """Return issues for local Markdown links missing from a committed tree."""
    available = {str(path).replace("\\", "/") for path in tree_paths}
    issues: list[ReleaseIssue] = []
    for match in LOCAL_LINK_PATTERN.finditer(markdown):
        target = match.group(1).strip()
        if target.startswith("<") and target.endswith(">"):
            target = target[1:-1]
        if not target or target.startswith(("#", "/", "http://", "https://", "mailto:")):
            continue
        target = target.split("#", 1)[0].replace("\\", "/")
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(source_path), target))
        if resolved not in available:
            issues.append(
                ReleaseIssue(
                    source_path,
                    "link",
                    f"local Markdown target is missing from {source_path}: {target}",
                )
            )
    return issues


def find_ci_contract_issues(workflow: str) -> list[ReleaseIssue]:
    return [
        ReleaseIssue(
            ".github/workflows/ci.yml",
            "ci",
            f"required CI command is missing: {command}",
        )
        for command in REQUIRED_CI_COMMANDS
        if command not in workflow
    ]


def check_release_readiness(root: str | Path, ref: str = "HEAD") -> list[ReleaseIssue]:
    """Run non-publishing checks against the exact committed release tree."""
    repository = Path(root).resolve()
    tree_paths = _git_tree_paths(repository, ref)
    issues = audit_public_release_git_tree(repository, ref)

    readme = _git_show(repository, ref, "README.md")
    if readme is None:
        issues.append(ReleaseIssue("README.md", "missing", "README.md is absent from the release tree"))
    else:
        issues.extend(find_local_link_issues(readme, tree_paths))

    workflow = _git_show(repository, ref, ".github/workflows/ci.yml")
    if workflow is None:
        issues.append(
            ReleaseIssue(
                ".github/workflows/ci.yml",
                "missing",
                "CI workflow is absent from the release tree",
            )
        )
    else:
        issues.extend(find_ci_contract_issues(workflow))

    return sorted(set(issues), key=lambda issue: (issue.path, issue.category, issue.message))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--ref", default="HEAD", help="committed Git ref to inspect")
    parser.add_argument("--json", action="store_true", help="print a machine-readable report")
    args = parser.parse_args()

    issues = check_release_readiness(args.root, args.ref)
    report = {"status": "blocked" if issues else "passed", "issues": [asdict(issue) for issue in issues]}
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif issues:
        for issue in issues:
            print(f"{issue.category}: {issue.path}: {issue.message}")
    else:
        print(f"committed release-tree preflight passed for {args.ref}")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
