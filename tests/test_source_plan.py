from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import download_sources  # noqa: E402
from download_sources import build_plan, execute_plan  # noqa: E402

from baselines.piguard import PIGuardBaseline  # noqa: E402


def test_source_plan_is_pinned_and_preview_has_no_side_effect(tmp_path: Path) -> None:
    destination = tmp_path / "raw"

    plan = build_plan(["bipia", "injecagent", "notinject"], destination)

    assert not destination.exists()
    assert all(len(item["revision"]) == 40 for item in plan)
    assert {item["method"] for item in plan} == {"git", "huggingface_snapshot"}
    notinject = next(item for item in plan if item["name"] == "notinject")
    assert notinject["official_url"] == "https://huggingface.co/datasets/leolee99/NotInject"


def test_source_manifest_ignores_python_import_caches(tmp_path: Path) -> None:
    source = tmp_path / "source"
    cache = source / "package" / "__pycache__"
    cache.mkdir(parents=True)
    (source / "tracked.py").write_text("value = 1\n", encoding="utf-8")
    (cache / "tracked.cpython-312.pyc").write_bytes(b"cache")

    files = download_sources._artifact_files(source)

    assert [item["path"] for item in files] == ["tracked.py"]


def test_resume_reuses_verified_git_and_downloads_missing_snapshot(
    tmp_path: Path, monkeypatch
) -> None:
    destination = tmp_path / "raw"
    bipia = destination / "bipia"
    bipia.mkdir(parents=True)
    (bipia / "README.md").write_text("pinned git source\n", encoding="utf-8")
    plan = build_plan(["bipia", "notinject"], destination)
    validated: list[str] = []

    def fake_validate(item, target) -> None:
        assert target == bipia
        validated.append(item["name"])

    def fake_snapshot(item, target) -> None:
        target.mkdir(parents=True)
        (target / "data.parquet").write_bytes(b"fixture")

    monkeypatch.setattr(download_sources, "_validate_existing_git_source", fake_validate)
    monkeypatch.setattr(download_sources, "_run_huggingface_download", fake_snapshot)

    manifest = execute_plan(plan, destination, resume=True)

    assert validated == ["bipia"]
    assert [source["retrieval_status"] for source in manifest["sources"]] == [
        "reused_verified",
        "downloaded",
    ]
    assert (destination / "source_manifest.json").is_file()
    assert not (destination / "source_manifest.json.tmp").exists()


def test_resume_rejects_unmanifested_existing_snapshot(tmp_path: Path) -> None:
    destination = tmp_path / "raw"
    (destination / "notinject").mkdir(parents=True)
    plan = build_plan(["notinject"], destination)

    with pytest.raises(RuntimeError, match="no completed manifest entry"):
        execute_plan(plan, destination, resume=True)


def test_existing_source_still_requires_explicit_resume(tmp_path: Path) -> None:
    destination = tmp_path / "raw"
    (destination / "bipia").mkdir(parents=True)
    plan = build_plan(["bipia"], destination)

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        execute_plan(plan, destination)


@pytest.mark.parametrize(
    ("outputs", "message"),
    [
        (["b" * 40], "expected revision"),
        (["a" * 40, " M README.md"], "local changes"),
    ],
)
def test_resume_rejects_wrong_or_dirty_git_source(
    tmp_path: Path, monkeypatch, outputs: list[str], message: str
) -> None:
    target = tmp_path / "bipia"
    (target / ".git").mkdir(parents=True)
    responses = iter(outputs)

    def fake_run(*args, **kwargs):
        return SimpleNamespace(stdout=next(responses))

    monkeypatch.setattr(download_sources.subprocess, "run", fake_run)
    item = {"name": "bipia", "revision": "a" * 40}

    with pytest.raises(RuntimeError, match=message):
        download_sources._validate_existing_git_source(item, target)


def test_piguard_uses_pinned_reviewable_remote_code(monkeypatch) -> None:
    captured = {}

    def fake_pipeline(*args, **kwargs):
        captured.update(kwargs)
        return lambda texts, **call_kwargs: [
            [{"label": "benign", "score": 0.2}, {"label": "injection", "score": 0.8}] for _ in texts
        ]

    monkeypatch.setitem(sys.modules, "transformers", SimpleNamespace(pipeline=fake_pipeline))
    baseline = PIGuardBaseline(model_name="owner/model", revision="a" * 40)

    assert captured["revision"] == "a" * 40
    assert captured["trust_remote_code"] is True
    assert baseline.attack_scores(["text"]) == [0.8]
