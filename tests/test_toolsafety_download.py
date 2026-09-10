from __future__ import annotations

import hashlib
import io
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import download_candidate_9_toolsafety as downloader  # noqa: E402


def configure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, approved: bool = True) -> None:
    (tmp_path / "configs").mkdir()
    (tmp_path / "data/raw").mkdir(parents=True)
    config = {
        "owner_approved_download_and_readonly_audit": approved,
        "repository": "jinjinyien/ToolSafety",
        "revision": "7c444473e0dc0a822247858c249b10856ade04ef",
        "data_file": "toolsafety.json",
        "expected_bytes": 2,
        "expected_sha256": hashlib.sha256(b"[]").hexdigest(),
    }
    (tmp_path / "configs/candidate_9_toolsafety_audit.yaml").write_text(
        yaml.safe_dump(config), encoding="utf-8"
    )
    monkeypatch.setattr(downloader, "ROOT", tmp_path)


def test_unapproved_download_cannot_open_network(tmp_path, monkeypatch) -> None:
    configure(tmp_path, monkeypatch, approved=False)

    def unexpected_network(*args, **kwargs):
        pytest.fail("An unapproved source must not reach the network")

    monkeypatch.setattr(downloader.urllib.request, "urlopen", unexpected_network)
    with pytest.raises(ValueError, match="not approved"):
        downloader.download()
    assert not (tmp_path / "data/raw/toolsafety").exists()


@pytest.mark.parametrize("payload", [b"{}", b"[1]"])
def test_corrupt_or_oversized_data_never_gets_a_verified_manifest(tmp_path, monkeypatch, payload):
    configure(tmp_path, monkeypatch)
    monkeypatch.setattr(
        downloader.urllib.request,
        "urlopen",
        lambda url, timeout: io.BytesIO(b"license: mit" if url.endswith("README.md") else payload),
    )
    with pytest.raises(ValueError, match="size|hash"):
        downloader.download()
    target = tmp_path / "data/raw/toolsafety"
    assert not (target / "source_manifest.json").exists()
    assert not (target / "toolsafety.json").exists()
    assert (target / "toolsafety.json.partial").exists()
