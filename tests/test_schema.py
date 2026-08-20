from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from intentfence.schema import IntentSample, read_jsonl


def make_sample(**updates):
    payload = {
        "sample_id": "one",
        "source": "test",
        "scenario": "web",
        "user_goal": "summarize",
        "untrusted_content": "public content",
        "proposed_action": "return_summary()",
        "risk_label": "benign",
        "alignment_label": 0,
        "severity": 0,
        "template_group": "g1",
    }
    payload.update(updates)
    return IntentSample(**payload)


def test_coherent_labels_required():
    with pytest.raises(ValidationError):
        make_sample(risk_label="data_exfiltration", alignment_label=0)


def test_duplicate_ids_rejected(tmp_path):
    sample = make_sample().model_dump(mode="json")
    path = tmp_path / "samples.jsonl"
    path.write_text(json.dumps(sample) + "\n" + json.dumps(sample) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate sample_id"):
        read_jsonl(path)
