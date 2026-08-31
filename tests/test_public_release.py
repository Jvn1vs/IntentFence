from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.audit_public_release import audit_public_release, audit_public_release_git_tree

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_current_tracked_source_passes_public_release_audit() -> None:
    assert audit_public_release(REPOSITORY_ROOT) == []


def test_public_release_audit_rejects_artifacts_and_generated_caches(tmp_path: Path) -> None:
    paths = [
        "checkpoints/model.pt",
        "data/raw/private.jsonl",
        "reports/tables/metrics.json",
        ".env",
    ]

    issues = audit_public_release(tmp_path, paths=paths, require_documents=False)

    categories = {(issue.path, issue.category) for issue in issues}
    assert ("checkpoints/model.pt", "artifact") in categories
    assert ("checkpoints/model.pt", "weight") in categories
    assert ("data/raw/private.jsonl", "artifact") in categories
    assert ("reports/tables/metrics.json", "cache") in categories
    assert (".env", "credential") in categories


def test_public_release_audit_rejects_unlisted_data_and_model_formats(tmp_path: Path) -> None:
    paths = [
        "reports/private_metrics.csv",
        "exports/users.json",
        "predictions/final_test.parquet",
        "model.bin",
        "model.joblib",
        "unlisted.json",
    ]

    issues = audit_public_release(tmp_path, paths=paths, require_documents=False)

    categories = {(issue.path, issue.category) for issue in issues}
    assert ("reports/private_metrics.csv", "data") in categories
    assert ("exports/users.json", "artifact") in categories
    assert ("predictions/final_test.parquet", "data") in categories
    assert ("model.bin", "weight") in categories
    assert ("model.joblib", "weight") in categories
    assert ("unlisted.json", "data") in categories


def test_public_release_audit_requires_documents_when_requested(tmp_path: Path) -> None:
    issues = audit_public_release(tmp_path, paths=[], require_documents=True)

    missing = {issue.path for issue in issues if issue.category == "missing"}
    assert "README.md" in missing
    assert "docs/claim_evidence_matrix.md" in missing


def test_public_release_audit_can_include_nonignored_untracked_paths(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    unsafe = tmp_path / "predictions" / "final.json"
    unsafe.parent.mkdir()
    unsafe.write_text("{}", encoding="utf-8")

    assert audit_public_release(tmp_path, require_documents=False) == []
    issues = audit_public_release(
        tmp_path,
        include_untracked=True,
        require_documents=False,
    )

    categories = {(issue.path, issue.category) for issue in issues}
    assert ("predictions/final.json", "artifact") in categories
    assert ("predictions/final.json", "data") in categories


def test_public_release_audit_checks_the_committed_git_tree(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    unsafe = tmp_path / "model.bin"
    unsafe.write_bytes(b"not a model for this fixture")
    subprocess.run(["git", "add", "model.bin"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=IntentFence test",
            "-c",
            "user.email=intentfence-test@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "fixture",
        ],
        cwd=tmp_path,
        check=True,
    )

    issues = audit_public_release_git_tree(tmp_path, require_documents=False)

    assert ("model.bin", "weight") in {(issue.path, issue.category) for issue in issues}


def test_public_release_audit_detects_high_confidence_secret(tmp_path: Path) -> None:
    secret_file = tmp_path / "notes.txt"
    secret_file.write_text(
        "OPENAI_API_" + "KEY=" + "sk-live-" + "12345678901234567890\n",
        encoding="utf-8",
    )

    issues = audit_public_release(
        tmp_path,
        paths=["notes.txt"],
        require_documents=False,
    )

    assert any(issue.category == "secret" for issue in issues)


def test_public_release_audit_scans_large_and_binary_payloads(tmp_path: Path) -> None:
    secret_file = tmp_path / "notes.bin"
    secret_file.write_bytes(
        b"A" * (2 * 1024 * 1024)
        + b"\0OPENAI_API_"
        + b"KEY=sk-live-"
        + b"12345678901234567890"
    )

    issues = audit_public_release(
        tmp_path,
        paths=["notes.bin"],
        require_documents=False,
    )

    assert any(issue.category == "secret" for issue in issues)


def test_public_release_audit_allows_placeholders_and_synthetic_fixture() -> None:
    issues = audit_public_release(
        REPOSITORY_ROOT,
        paths=[".env.example", "data/examples/smoke.jsonl", "reports/tables/.gitkeep"],
        require_documents=False,
    )

    assert issues == []
