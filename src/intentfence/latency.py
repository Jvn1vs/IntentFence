from __future__ import annotations

import math
import os
import statistics
from collections.abc import Iterable


def _validate_optional_time(value: float | None, *, name: str) -> float | None:
    if value is None:
        return None
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0:
        raise ValueError(f"{name} must be a finite non-negative number")
    return numeric


def _percentile(values: list[float], percentage: float) -> float:
    position = (len(values) - 1) * percentage / 100.0
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    fraction = position - lower
    return values[lower] + (values[upper] - values[lower]) * fraction


def summarize_timings(
    timings: Iterable[float],
    *,
    initialization_ms: float | None = None,
    cold_request_ms: float | None = None,
    wall_time_ms: float | None = None,
    request_count: int | None = None,
) -> dict[str, float | int | None]:
    """Summarize request timings without retuning or filtering observations."""

    values = [float(value) for value in timings]
    if not values:
        raise ValueError("timings must contain at least one observation")
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError("timings must contain only finite non-negative values")
    if request_count is None:
        request_count = len(values)
    if (
        isinstance(request_count, bool)
        or not isinstance(request_count, int)
        or request_count <= 0
    ):
        raise ValueError("request_count must be a positive integer")
    if request_count != len(values):
        raise ValueError("request_count must equal the number of timing observations")

    initialization_ms = _validate_optional_time(initialization_ms, name="initialization_ms")
    cold_request_ms = _validate_optional_time(cold_request_ms, name="cold_request_ms")
    wall_time_ms = _validate_optional_time(wall_time_ms, name="wall_time_ms")
    ordered = sorted(values)
    mean_ms = statistics.fmean(values)
    result: dict[str, float | int | None] = {
        "request_count": request_count,
        "p50_ms": _percentile(ordered, 50.0),
        "p95_ms": _percentile(ordered, 95.0),
        "mean_ms": mean_ms,
        "stddev_ms": statistics.pstdev(values),
        "min_ms": ordered[0],
        "max_ms": ordered[-1],
        "throughput_rps": (
            float(request_count / (wall_time_ms / 1000.0))
            if wall_time_ms is not None and wall_time_ms > 0
            else (float(1000.0 / mean_ms) if mean_ms > 0 else None)
        ),
        "initialization_ms": initialization_ms,
        "cold_request_ms": cold_request_ms,
        "wall_time_ms": wall_time_ms,
    }
    return result


def peak_process_rss_bytes() -> int | None:
    """Return process peak resident memory when the host exposes it."""

    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("page_fault_count", ctypes.c_ulong),
                ("peak_working_set_size", ctypes.c_size_t),
                ("working_set_size", ctypes.c_size_t),
                ("quota_peak_paged_pool_usage", ctypes.c_size_t),
                ("quota_paged_pool_usage", ctypes.c_size_t),
                ("quota_peak_non_paged_pool_usage", ctypes.c_size_t),
                ("quota_non_paged_pool_usage", ctypes.c_size_t),
                ("pagefile_usage", ctypes.c_size_t),
                ("peak_pagefile_usage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(ProcessMemoryCounters)
        get_current_process = ctypes.windll.kernel32.GetCurrentProcess
        get_current_process.restype = wintypes.HANDLE
        get_process_memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
        get_process_memory_info.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ProcessMemoryCounters),
            wintypes.DWORD,
        ]
        get_process_memory_info.restype = wintypes.BOOL
        success = get_process_memory_info(
            get_current_process(),
            ctypes.byref(counters),
            counters.cb,
        )
        return int(counters.peak_working_set_size) if success else None

    try:
        import resource
        import sys

        value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    except (ImportError, AttributeError, OSError, ValueError):
        return None
    return value if sys.platform == "darwin" else value * 1024
