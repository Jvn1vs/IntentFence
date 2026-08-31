from __future__ import annotations

import math

import pytest

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
