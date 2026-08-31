from __future__ import annotations

import argparse
import json
import os
import platform
import time
import tracemalloc
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from intentfence.deployment import artifact_tree_sha256, sha256_file
from intentfence.inference import OnnxBackend, RuleBackend, TorchBackend
from intentfence.latency import peak_process_rss_bytes, summarize_timings

CASES = {
    "short": (
        "Summarize the page.",
        "The page contains public documentation and a short changelog.",
        "return_summary()",
    ),
    "medium": (
        "Summarize the page and identify the release impact.",
        "The page contains public documentation, a release changelog, migration notes, "
        "and examples of ordinary read-only usage.",
        "return_summary(include_release_impact=True)",
    ),
    "long": (
        "Summarize the page and identify the release impact.",
        " ".join(
            [
                "The page contains public documentation, a release changelog, migration notes, "
                "and examples of ordinary read-only usage."
            ]
            * 80
        ),
        "return_summary(include_release_impact=True)",
    ),
}


def _timed_prediction(backend: object, case: tuple[str, str, str]) -> float:
    started = time.perf_counter_ns()
    backend.predict(*case)  # type: ignore[attr-defined]
    return (time.perf_counter_ns() - started) / 1_000_000


def _model_path_for_onnx(model_dir: Path, variant: str) -> tuple[Path, str]:
    if variant == "auto":
        variant = "int8" if (model_dir / "model.int8.onnx").exists() else "fp32"
    path = model_dir / ("model.int8.onnx" if variant == "int8" else "model.onnx")
    if not path.is_file():
        raise FileNotFoundError(f"requested ONNX {variant} artifact does not exist: {path}")
    return path, variant


def _artifact_size_bytes(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _measure(
    backend: object,
    case: tuple[str, str, str],
    *,
    warmup: int,
    iterations: int,
    concurrency: int,
) -> dict[str, float | int | None]:
    for _ in range(warmup):
        backend.predict(*case)  # type: ignore[attr-defined]
    measured_started = time.perf_counter()
    if concurrency == 1:
        timings = [_timed_prediction(backend, case) for _ in range(iterations)]
    else:
        timings = []
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            remaining = iterations
            while remaining:
                batch_size = min(concurrency, remaining)
                futures = [
                    executor.submit(_timed_prediction, backend, case)
                    for _ in range(batch_size)
                ]
                timings.extend(future.result() for future in futures)
                remaining -= batch_size
    wall_time_ms = (time.perf_counter() - measured_started) * 1000
    return summarize_timings(
        timings,
        wall_time_ms=wall_time_ms,
        request_count=iterations,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure cold, warmed, and optionally concurrent CPU request latency"
    )
    parser.add_argument("--backend", choices=("rules", "torch", "onnx"), default="rules")
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--calibration", type=Path)
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--case", choices=tuple(CASES), default="short")
    parser.add_argument(
        "--onnx-variant",
        choices=("int8", "fp32", "auto"),
        default="int8",
        help="ONNX artifact to measure; auto selects INT8 when available",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.iterations <= 0:
        parser.error("--iterations must be positive")
    if args.warmup < 0:
        parser.error("--warmup must be non-negative")
    if args.concurrency <= 0:
        parser.error("--concurrency must be positive")
    if args.backend in {"torch", "onnx"} and args.model_dir is None:
        parser.error(f"--model-dir is required for the {args.backend} backend")
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite latency report: {args.output}")
    if args.model_dir is not None:
        model_dir = args.model_dir.resolve()
        if not model_dir.is_dir():
            raise FileNotFoundError(f"model directory does not exist: {model_dir}")
        output_path = args.output.resolve()
        if output_path == model_dir or model_dir in output_path.parents:
            raise ValueError("latency report must be outside the model artifact directory")

    case = CASES[args.case]
    tracemalloc.start()
    initialization_started = time.perf_counter_ns()
    variant = "native"
    model_path: Path | None = None
    if args.backend == "torch":
        backend = TorchBackend(args.model_dir, args.calibration)
    elif args.backend == "onnx":
        model_path, variant = _model_path_for_onnx(args.model_dir, args.onnx_variant)
        backend = OnnxBackend(model_path, args.model_dir / "tokenizer", args.calibration)
    else:
        backend = RuleBackend()
    initialization_ms = (time.perf_counter_ns() - initialization_started) / 1_000_000

    cold_request_ms = _timed_prediction(backend, case)
    summary = _measure(
        backend,
        case,
        warmup=args.warmup,
        iterations=args.iterations,
        concurrency=args.concurrency,
    )
    summary["initialization_ms"] = initialization_ms
    summary["cold_request_ms"] = cold_request_ms
    _, peak_python_allocated_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    model_artifact_sha256 = None
    model_artifact_size_bytes = None
    if args.model_dir is not None:
        model_artifact_sha256 = artifact_tree_sha256(args.model_dir)
        model_artifact_size_bytes = _artifact_size_bytes(args.model_dir)
    calibration_sha256 = None
    if args.calibration is not None and args.calibration.is_file():
        calibration_sha256 = sha256_file(args.calibration)
    result = {
        "backend": backend.name,
        "model_version": getattr(backend, "model_version", backend.name),
        "model_revision": getattr(backend, "model_revision", None),
        "onnx_variant": variant if args.backend == "onnx" else None,
        "model_path": str(model_path.resolve()) if model_path is not None else None,
        "model_artifact_sha256": model_artifact_sha256,
        "model_artifact_size_bytes": model_artifact_size_bytes,
        "calibration_path": str(args.calibration.resolve()) if args.calibration else None,
        "calibration_sha256": calibration_sha256,
        "input_case": args.case,
        "concurrency": args.concurrency,
        "warmup": args.warmup,
        "iterations": args.iterations,
        **summary,
        "peak_python_allocated_bytes": peak_python_allocated_bytes,
        "peak_process_rss_bytes": peak_process_rss_bytes(),
        "memory_note": "process peak RSS is host-level; Python allocation peak excludes native tensors",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER"),
        "cpu_count": os.cpu_count(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
