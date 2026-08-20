from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from download_sources import build_plan  # noqa: E402

from baselines.piguard import PIGuardBaseline  # noqa: E402


def test_source_plan_is_pinned_and_preview_has_no_side_effect(tmp_path: Path) -> None:
    destination = tmp_path / "raw"

    plan = build_plan(["bipia", "injecagent", "notinject"], destination)

    assert not destination.exists()
    assert all(len(item["revision"]) == 40 for item in plan)
    assert {item["method"] for item in plan} == {"git", "huggingface_snapshot"}
    notinject = next(item for item in plan if item["name"] == "notinject")
    assert notinject["official_url"] == "https://huggingface.co/datasets/leolee99/NotInject"


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
