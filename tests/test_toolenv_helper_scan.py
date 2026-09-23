"""Literal ToolEnv helper scan reads bounded archives without extraction."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from intentfence.toolenv_helper_scan import scan_helper_names


def make_archive(path: Path, entries: list[tuple[str, bytes]]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for name, content in entries:
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))


def test_finds_literal_name_without_extracting(tmp_path: Path) -> None:
    archive = tmp_path / "tools.tar.gz"
    make_archive(archive, [
        ("safe/a.json", b'{"name":"find_relevant_news_source"}'),
        ("safe/b.json", b'{"name":"other"}'),
        ("safe/.json", b'{"name":"missing"}'),
    ])
    result = scan_helper_names(archive, {"find_relevant_news_source", "missing"})
    assert result["json_files_scanned"] == 3
    assert result["hits"][0]["literal_names_found"] == ["find_relevant_news_source"]
    assert result["hits"][1]["literal_names_found"] == ["missing"]
    assert result["extracted_files"] == 0
    assert not (tmp_path / "safe").exists()


@pytest.mark.parametrize("entries,error", [
    ([("../escape.json", b"x")], "unsafe"),
    ([("safe/a.json", b"x"), ("safe/a.json", b"y")], "duplicate"),
])
def test_rejects_unsafe_or_duplicate_members(
    tmp_path: Path, entries: list[tuple[str, bytes]], error: str
) -> None:
    archive = tmp_path / "tools.tar.gz"
    make_archive(archive, entries)
    with pytest.raises(ValueError, match=error):
        scan_helper_names(archive, {"helper"})


def test_rejects_oversized_json(tmp_path: Path) -> None:
    archive = tmp_path / "tools.tar.gz"
    make_archive(archive, [("safe/a.json", b"12345")])
    with pytest.raises(ValueError, match="oversized"):
        scan_helper_names(archive, {"helper"}, max_json=4)
