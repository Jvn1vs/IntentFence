from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import export_bipia_builder as builder_export  # noqa: E402

REVISION = "a" * 40
BUILDER_BYTES = b'{"row":1}\n{"row":2}\n'


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture_paths(tmp_path: Path) -> dict[str, Path]:
    bipia_root = tmp_path / "bipia"
    contexts = bipia_root / "benchmark" / "email" / "train.jsonl"
    attacks = bipia_root / "benchmark" / "text_attack_train.json"
    contexts.parent.mkdir(parents=True)
    contexts.write_text('{"question":"q","context":"c"}\n', encoding="utf-8")
    attacks.write_text('{"attack":["ignore"]}\n', encoding="utf-8")
    source_manifest = tmp_path / "source_manifest.json"
    source_manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sources": [
                    {
                        "name": "bipia",
                        "revision": REVISION,
                        "target": str(bipia_root.resolve()),
                        "files": [
                            {
                                "path": contexts.relative_to(bipia_root).as_posix(),
                                "size": contexts.stat().st_size,
                                "sha256": _sha256(contexts),
                            },
                            {
                                "path": attacks.relative_to(bipia_root).as_posix(),
                                "size": attacks.stat().st_size,
                                "sha256": _sha256(attacks),
                            },
                        ],
                    }
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    output = tmp_path / "interim" / "bipia_email_attack_train.jsonl"
    return {
        "bipia_root": bipia_root,
        "contexts": contexts,
        "attacks": attacks,
        "source_manifest": source_manifest,
        "output": output,
        "report": output.with_suffix(".builder.json"),
    }


def _argv(paths: dict[str, Path], mode: str, *extra: str) -> list[str]:
    return [
        "export_bipia_builder.py",
        "--bipia-root",
        str(paths["bipia_root"]),
        "--task",
        "email",
        "--contexts",
        str(paths["contexts"]),
        "--attacks",
        str(paths["attacks"]),
        "--output",
        str(paths["output"]),
        "--source-manifest",
        str(paths["source_manifest"]),
        mode,
        *extra,
    ]


def _install_success_mocks(monkeypatch: pytest.MonkeyPatch, payload: bytes = BUILDER_BYTES) -> None:
    monkeypatch.setattr(builder_export, "_expected_revision", lambda: REVISION)
    monkeypatch.setattr(builder_export, "_head", lambda _path: REVISION)
    monkeypatch.setattr(builder_export, "_worktree_status", lambda _path: "")

    def fake_builder(**kwargs: Any) -> int:
        assert kwargs["task"] == "email"
        assert kwargs["seed"] == 42
        kwargs["output"].write_bytes(payload)
        return len(payload.splitlines())

    monkeypatch.setattr(builder_export, "_run_builder", fake_builder)


def test_execute_writes_verified_output_and_atomic_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _fixture_paths(tmp_path)
    _install_success_mocks(monkeypatch)
    monkeypatch.setattr(sys, "argv", _argv(paths, "--execute"))

    builder_export.main()

    assert paths["output"].read_bytes() == BUILDER_BYTES
    report = json.loads(paths["report"].read_text(encoding="utf-8"))
    assert report["status"] == "generated_verified"
    assert report["execution_owner"] == "project_owner"
    assert report["task"] == "email"
    assert report["seed"] == 42
    assert report["expected_revision"] == REVISION
    assert report["actual_revision"] == REVISION
    assert report["source_manifest"] == {
        "path": str(paths["source_manifest"].resolve()),
        "file_sha256": _sha256(paths["source_manifest"]),
    }
    assert report["contexts"]["path"] == str(paths["contexts"].resolve())
    assert report["contexts"]["size"] == paths["contexts"].stat().st_size
    assert report["contexts"]["sha256"] == _sha256(paths["contexts"])
    assert report["attacks"]["path"] == str(paths["attacks"].resolve())
    assert report["output"] == {
        "path": str(paths["output"].resolve()),
        "rows": 2,
        "sha256": _sha256(paths["output"]),
    }
    assert report["environment"]["python"]
    assert set(report["environment"]["packages"]) == set(
        builder_export.PACKAGE_DISTRIBUTIONS
    )
    assert not list(paths["output"].parent.glob("*.tmp"))


def test_verify_existing_reproduces_bytes_and_rows_without_modifying_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _fixture_paths(tmp_path)
    paths["output"].parent.mkdir(parents=True)
    paths["output"].write_bytes(BUILDER_BYTES)
    original_bytes = paths["output"].read_bytes()
    original_mtime = paths["output"].stat().st_mtime_ns
    _install_success_mocks(monkeypatch)
    monkeypatch.setattr(sys, "argv", _argv(paths, "--verify-existing"))

    builder_export.main()

    assert paths["output"].read_bytes() == original_bytes
    assert paths["output"].stat().st_mtime_ns == original_mtime
    report = json.loads(paths["report"].read_text(encoding="utf-8"))
    assert report["status"] == "reproduced_verified"
    assert report["output"]["rows"] == 2
    assert report["output"]["sha256"] == _sha256(paths["output"])
    assert report["reproduction"] == {
        "rows": report["output"]["rows"],
        "sha256": report["output"]["sha256"],
    }


def test_verify_existing_mismatch_preserves_output_and_writes_no_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _fixture_paths(tmp_path)
    paths["output"].parent.mkdir(parents=True)
    paths["output"].write_bytes(BUILDER_BYTES)
    original = paths["output"].read_bytes()
    _install_success_mocks(monkeypatch, b'{"different":1}\n')
    monkeypatch.setattr(sys, "argv", _argv(paths, "--verify-existing"))

    with pytest.raises(ValueError, match="reproduction mismatch"):
        builder_export.main()

    assert paths["output"].read_bytes() == original
    assert not paths["report"].exists()


def test_revision_mismatch_stops_before_builder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _fixture_paths(tmp_path)
    monkeypatch.setattr(builder_export, "_expected_revision", lambda: REVISION)
    monkeypatch.setattr(builder_export, "_head", lambda _path: "b" * 40)
    monkeypatch.setattr(
        builder_export,
        "_run_builder",
        lambda **_kwargs: pytest.fail("builder must not run on revision mismatch"),
    )
    monkeypatch.setattr(sys, "argv", _argv(paths, "--execute"))

    with pytest.raises(RuntimeError, match="revision mismatch"):
        builder_export.main()

    assert not paths["output"].exists()
    assert not paths["report"].exists()


def test_manifest_input_mismatch_stops_before_builder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _fixture_paths(tmp_path)
    paths["contexts"].write_text("tampered\n", encoding="utf-8")
    monkeypatch.setattr(builder_export, "_expected_revision", lambda: REVISION)
    monkeypatch.setattr(builder_export, "_head", lambda _path: REVISION)
    monkeypatch.setattr(builder_export, "_worktree_status", lambda _path: "")
    monkeypatch.setattr(
        builder_export,
        "_run_builder",
        lambda **_kwargs: pytest.fail("builder must not run on manifest mismatch"),
    )
    monkeypatch.setattr(sys, "argv", _argv(paths, "--execute"))

    with pytest.raises(RuntimeError, match="does not match source manifest"):
        builder_export.main()

    assert not paths["output"].exists()
    assert not paths["report"].exists()


def test_existing_report_is_never_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _fixture_paths(tmp_path)
    paths["output"].parent.mkdir(parents=True)
    paths["output"].write_bytes(BUILDER_BYTES)
    paths["report"].write_text("existing evidence\n", encoding="utf-8")
    monkeypatch.setattr(builder_export, "_expected_revision", lambda: REVISION)
    monkeypatch.setattr(sys, "argv", _argv(paths, "--verify-existing"))

    with pytest.raises(FileExistsError, match="Refusing to overwrite builder report"):
        builder_export.main()

    assert paths["report"].read_text(encoding="utf-8") == "existing evidence\n"
    assert paths["output"].read_bytes() == BUILDER_BYTES


def test_execute_and_verify_existing_are_mutually_exclusive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _fixture_paths(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        _argv(paths, "--execute", "--verify-existing"),
    )

    with pytest.raises(SystemExit) as exc_info:
        builder_export.main()

    assert exc_info.value.code == 2
