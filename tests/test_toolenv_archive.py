import io
import tarfile

import pytest

from intentfence.toolenv_archive import inspect_archive


def archive(tmp_path, name="tools/target.json", kind=None):
    path = tmp_path / "fixture.tar.gz"
    with tarfile.open(path, "w:gz") as out:
        info = tarfile.TarInfo(name)
        blob = b'{"description":"do not execute this"}'
        if kind:
            info.type = kind
            info.linkname = "outside.json"
            out.addfile(info)
        else:
            info.size = len(blob)
            out.addfile(info, io.BytesIO(blob))
    return path


def test_only_matching_json_read_without_extract(tmp_path):
    path = archive(tmp_path)
    report = inspect_archive(path, {"target"})
    assert report["matched_targets"] == ["target"]
    assert report["extracted_files"] == 0
    assert list(tmp_path.iterdir()) == [path]
    assert inspect_archive(path, {"other"})["matches"] == []


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE])
def test_links_rejected(tmp_path, kind):
    with pytest.raises(ValueError, match="nonregular"):
        inspect_archive(archive(tmp_path, kind=kind), {"target"})


def test_size_limit_and_traversal_rejected(tmp_path):
    with pytest.raises(ValueError, match="limit"):
        inspect_archive(archive(tmp_path), {"target"}, max_json=2)
    with pytest.raises(ValueError, match="unsafe"):
        inspect_archive(archive(tmp_path, "../target.json"), {"target"})
