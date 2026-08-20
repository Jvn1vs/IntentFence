from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from intentfence.constants import RISK_LABELS, SPLIT_NAMES


class IntentSample(BaseModel):
    """Canonical, versioned sample used by every pipeline stage."""

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    sample_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    scenario: str = "unknown"
    user_goal: str = ""
    untrusted_content: str
    proposed_action: str = ""
    risk_label: Literal[
        "benign",
        "instruction_hijacking",
        "data_exfiltration",
        "privilege_escalation",
        "tool_manipulation",
    ]
    alignment_label: Literal[0, 1]
    attack_family: str = "none"
    severity: int = Field(default=0, ge=0, le=4)
    template_group: str = Field(min_length=1)
    split: (
        Literal["train", "validation", "calibration", "test_a", "test_b", "test_c", "test_d"] | None
    ) = None
    language: str = "en"
    human_verified: bool = False
    source_record_id: str | None = None
    adapter_profile: str = "unknown"
    adapter_missing_action: bool = False
    action_provenance: Literal[
        "missing", "benchmark_target", "protocol_wrapper", "source_field", "unknown"
    ] = "unknown"
    label_provenance: str = "unknown"
    field_provenance: dict[str, list[str]] = Field(default_factory=dict)

    @field_validator("risk_label")
    @classmethod
    def known_risk_label(cls, value: str) -> str:
        if value not in RISK_LABELS:
            raise ValueError(f"risk_label must be one of {RISK_LABELS}")
        return value

    @field_validator("split")
    @classmethod
    def known_split(cls, value: str | None) -> str | None:
        if value is not None and value not in SPLIT_NAMES:
            raise ValueError(f"split must be one of {SPLIT_NAMES}")
        return value

    @model_validator(mode="after")
    def labels_are_coherent(self) -> IntentSample:
        if self.risk_label == "benign" and self.alignment_label != 0:
            raise ValueError("benign samples must have alignment_label=0")
        if self.risk_label != "benign" and self.alignment_label != 1:
            raise ValueError("risk samples must have alignment_label=1")
        if self.risk_label == "benign" and self.severity > 1:
            raise ValueError("benign samples cannot have severity above 1")
        return self

    @property
    def attack_label(self) -> int:
        return int(self.risk_label != "benign")


class PredictionRecord(BaseModel):
    sample_id: str
    risk_probabilities: dict[str, float]
    alignment_conflict_probability: float
    predicted_risk: str
    attack_score: float
    backend: str


def read_jsonl(path: str | Path) -> list[IntentSample]:
    source_path = Path(path)
    samples: list[IntentSample] = []
    seen_ids: set[str] = set()
    with source_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                sample = IntentSample.model_validate_json(line)
            except Exception as exc:
                raise ValueError(f"Invalid sample at {source_path}:{line_number}: {exc}") from exc
            if sample.sample_id in seen_ids:
                raise ValueError(
                    f"Duplicate sample_id at {source_path}:{line_number}: {sample.sample_id}"
                )
            seen_ids.add(sample.sample_id)
            samples.append(sample)
    return samples


def iter_json_objects(path: str | Path) -> Iterator[dict[str, Any]]:
    """Read JSONL/JSON or a Parquet file using the optional data dependencies."""

    source_path = Path(path)
    if source_path.suffix.lower() == ".parquet":
        try:
            import pyarrow.parquet as parquet
        except ImportError as exc:
            raise RuntimeError(
                "Install intentfence[data] before reading upstream Parquet files"
            ) from exc
        for batch in parquet.ParquetFile(source_path).iter_batches(batch_size=1_024):
            yield from batch.to_pylist()
        return
    if source_path.suffix.lower() == ".jsonl":
        with source_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield json.loads(line)
        return

    payload = json.loads(source_path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        yield from payload
        return
    if isinstance(payload, dict):
        for key in ("data", "records", "samples", "examples", "tasks"):
            if isinstance(payload.get(key), list):
                yield from payload[key]
                return
        yield payload
        return
    raise ValueError(f"Unsupported JSON shape in {source_path}")


def write_jsonl(
    samples: Iterable[IntentSample | BaseModel | dict[str, Any]], path: str | Path
) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for sample in samples:
            payload = sample.model_dump(mode="json") if isinstance(sample, BaseModel) else sample
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
