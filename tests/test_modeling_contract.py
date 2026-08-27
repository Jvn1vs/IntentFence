from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np

import intentfence.modeling as modeling

MODEL_REVISION = "a36c739020e01763fe789b4b85e2df55d6180012"


class FakeModule:
    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self.forward(*args, **kwargs)


class FakeDropout(FakeModule):
    def __init__(self, probability: float) -> None:
        self.p = probability

    def forward(self, values: np.ndarray) -> np.ndarray:
        return values


class FakeLinear(FakeModule):
    def __init__(self, input_size: int, output_size: int) -> None:
        self.input_size = input_size
        self.output_size = output_size
        self.loaded_state: dict[str, Any] | None = None

    def forward(self, values: np.ndarray) -> np.ndarray:
        return np.zeros((values.shape[0], self.output_size), dtype=np.float32)

    def state_dict(self) -> dict[str, int]:
        return {"input_size": self.input_size, "output_size": self.output_size}

    def load_state_dict(self, state: dict[str, Any]) -> None:
        self.loaded_state = state


class FakeEncoder(FakeModule):
    def __init__(self) -> None:
        self.config = SimpleNamespace(
            hidden_size=7,
            hidden_dropout_prob=0.25,
            type_vocab_size=0,
        )
        self.last_kwargs: dict[str, Any] = {}

    def forward(self, **kwargs: Any) -> Any:
        self.last_kwargs = kwargs
        input_ids = kwargs["input_ids"]
        return SimpleNamespace(
            last_hidden_state=np.zeros((*input_ids.shape, self.config.hidden_size), dtype=np.float32)
        )

    def save_pretrained(self, destination: Path) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "fake_encoder.json").write_text("{}\n", encoding="utf-8")


class FakeAutoModel:
    calls: list[tuple[str, dict[str, Any]]] = []

    @classmethod
    def from_pretrained(cls, model_name: str | Path, **kwargs: Any) -> FakeEncoder:
        cls.calls.append((str(model_name), kwargs))
        return FakeEncoder()


class FakeTokenizer:
    def save_pretrained(self, destination: Path) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "fake_tokenizer.json").write_text("{}\n", encoding="utf-8")


class FakeAutoTokenizer:
    @classmethod
    def from_pretrained(cls, _source: str | Path) -> FakeTokenizer:
        return FakeTokenizer()


class FakeTorch:
    @staticmethod
    def save(payload: dict[str, Any], destination: Path) -> None:
        destination.write_text(json.dumps(payload), encoding="utf-8")

    @staticmethod
    def load(
        source: Path, *, map_location: str, weights_only: bool
    ) -> dict[str, Any]:
        assert map_location == "cpu"
        assert weights_only is True
        return json.loads(source.read_text(encoding="utf-8"))


def test_model_shapes_revision_and_checkpoint_reload_are_mock_verified(
    monkeypatch: Any, tmp_path: Path
) -> None:
    fake_nn = SimpleNamespace(
        Module=FakeModule,
        Dropout=FakeDropout,
        Linear=FakeLinear,
    )
    monkeypatch.setattr(
        modeling,
        "_require_ml",
        lambda: (FakeTorch, fake_nn, FakeAutoModel),
    )
    transformers = ModuleType("transformers")
    transformers.AutoTokenizer = FakeAutoTokenizer
    monkeypatch.setitem(sys.modules, "transformers", transformers)
    FakeAutoModel.calls.clear()

    model = modeling.create_multitask_model(
        "microsoft/deberta-v3-small",
        revision=MODEL_REVISION,
        num_risk_labels=5,
    )
    input_ids = np.zeros((2, 11), dtype=np.int64)
    attention_mask = np.ones((2, 11), dtype=np.int64)
    output = model(
        input_ids=input_ids,
        attention_mask=attention_mask,
        token_type_ids=np.zeros((2, 11), dtype=np.int64),
    )

    assert output["risk_logits"].shape == (2, 5)
    assert output["alignment_logits"].shape == (2, 2)
    assert "token_type_ids" not in model.encoder.last_kwargs
    assert FakeAutoModel.calls[0] == (
        "microsoft/deberta-v3-small",
        {"revision": MODEL_REVISION},
    )

    metadata = modeling.ModelMetadata(
        model_name="microsoft/deberta-v3-small",
        model_revision=MODEL_REVISION,
        risk_labels=(
            "benign",
            "instruction_hijacking",
            "data_exfiltration",
            "privilege_escalation",
            "tool_manipulation",
        ),
        input_mode="action",
        max_length=256,
        alignment_loss_weight=0.5,
    )
    modeling.save_multitask_model(model, FakeTokenizer(), metadata, tmp_path)
    loaded_model, loaded_tokenizer, loaded_metadata = modeling.load_multitask_model(tmp_path)

    assert isinstance(loaded_tokenizer, FakeTokenizer)
    assert loaded_metadata == metadata
    assert loaded_model.risk_head.loaded_state == model.risk_head.state_dict()
    assert loaded_model.alignment_head.loaded_state == model.alignment_head.state_dict()
    assert FakeAutoModel.calls[-1] == (str(tmp_path / "encoder"), {})
