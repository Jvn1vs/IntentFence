from __future__ import annotations

from pathlib import Path

from scripts.check_release_readiness import (
    REQUIRED_CI_COMMANDS,
    check_release_readiness,
    find_ci_contract_issues,
    find_local_link_issues,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_current_committed_release_tree_is_ready() -> None:
    assert check_release_readiness(REPOSITORY_ROOT, "HEAD") == []


def test_local_link_check_detects_missing_targets() -> None:
    issues = find_local_link_issues(
        "See [present](docs/present.md) and [missing](docs/missing.md#section).",
        {"README.md", "docs/present.md"},
    )

    assert [(issue.category, issue.path) for issue in issues] == [("link", "README.md")]


def test_ci_contract_check_reports_missing_commands() -> None:
    issues = find_ci_contract_issues(f"- run: {REQUIRED_CI_COMMANDS[0]}")

    assert len(issues) == len(REQUIRED_CI_COMMANDS) - 1
    assert all(issue.category == "ci" for issue in issues)


def test_ci_contract_ignores_comments_and_echo_text() -> None:
    workflow = "\n".join(
        [
            f"# {command}" for command in REQUIRED_CI_COMMANDS
        ]
        + ["- run: echo 'python -m pytest'", "- run: python -m ruff check ."]
    )

    issues = find_ci_contract_issues(workflow)

    missing = {issue.message for issue in issues}
    assert any("python -m pytest" in message for message in missing)
    assert any("python -m build --wheel" in message for message in missing)
