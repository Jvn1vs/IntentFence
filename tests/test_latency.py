from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

from benchmarks import latency
from intentfence.latency import summarize_timings


def test_summarize_timings_reports_percentiles_and_throughput() -> None:
    result = summarize_timings(
        [1.0, 2.0, 3.0, 4.0],
        initialization_ms=10.0,
        cold_request_ms=8.0,
        wall_time_ms=20.0,
    )

    assert result["request_count"] == 4
    assert result["p50_ms"] == pytest.approx(2.5)
    assert result["p95_ms"] == pytest.approx(3.85)
    assert result["throughput_rps"] == pytest.approx(200.0)
    assert result["initialization_ms"] == 10.0
    assert result["cold_request_ms"] == 8.0


@pytest.mark.parametrize("timings", ([], [-1.0], [math.nan], [math.inf]))
def test_summarize_timings_rejects_invalid_observations(timings: list[float]) -> None:
    with pytest.raises(ValueError):
        summarize_timings(timings)


def test_summarize_timings_rejects_mismatched_request_count() -> None:
    with pytest.raises(ValueError, match="request_count"):
        summarize_timings([1.0, 2.0], request_count=1)


def test_latency_preflight_is_read_only_for_rules_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "reports" / "latency.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "latency.py",
            "--backend",
            "rules",
            "--output",
            str(output),
            "--preflight-only",
        ],
    )

    latency.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "preflight_passed"
    assert payload["backend"] == "rules"
    assert payload["onnx_variant"] is None
    assert payload["output"] == str(output.resolve())
    assert not output.exists()
    assert not output.parent.exists()


def test_latency_preflight_rejects_missing_onnx_variant_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_dir = tmp_path / "export"
    (model_dir / "tokenizer").mkdir(parents=True)
    (model_dir / "model.onnx").write_bytes(b"fixture fp32")
    output = tmp_path / "reports" / "latency.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "latency.py",
            "--backend",
            "onnx",
            "--model-dir",
            str(model_dir),
            "--onnx-variant",
            "int8",
            "--output",
            str(output),
            "--preflight-only",
        ],
    )

    with pytest.raises(FileNotFoundError, match="int8"):
        latency.main()

    assert not output.exists()
    assert not output.parent.exists()


def test_latency_preflight_rejects_calibrated_onnx_without_export_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_dir = tmp_path / "export"
    (model_dir / "tokenizer").mkdir(parents=True)
    (model_dir / "model.onnx").write_bytes(b"fixture fp32")
    calibration = tmp_path / "calibration.json"
    calibration.write_text("{}\n", encoding="utf-8")
    output = tmp_path / "reports" / "latency.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "latency.py",
            "--backend",
            "onnx",
            "--model-dir",
            str(model_dir),
            "--calibration",
            str(calibration),
            "--onnx-variant",
            "fp32",
            "--output",
            str(output),
            "--preflight-only",
        ],
    )

    with pytest.raises(ValueError, match="hash-bound export_metadata"):
        latency.main()

    assert not output.exists()
    assert not output.parent.exists()
