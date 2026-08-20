from __future__ import annotations

import argparse
import json
import platform
import statistics
import time
from pathlib import Path

import numpy as np

from intentfence.inference import OnnxBackend, RuleBackend, TorchBackend


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure warmed single-request CPU latency")
    parser.add_argument("--backend", choices=("rules", "torch", "onnx"), default="rules")
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--calibration", type=Path)
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.backend == "torch":
        backend = TorchBackend(args.model_dir, args.calibration)
    elif args.backend == "onnx":
        model = args.model_dir / "model.int8.onnx"
        backend = OnnxBackend(model, args.model_dir / "tokenizer", args.calibration)
    else:
        backend = RuleBackend()
    case = (
        "Summarize the page.",
        "The page contains public documentation and a short changelog.",
        "return_summary()",
    )
    for _ in range(args.warmup):
        backend.predict(*case)
    timings = []
    for _ in range(args.iterations):
        started = time.perf_counter_ns()
        backend.predict(*case)
        timings.append((time.perf_counter_ns() - started) / 1_000_000)
    result = {
        "backend": backend.name,
        "iterations": args.iterations,
        "warmup": args.warmup,
        "p50_ms": float(np.percentile(timings, 50)),
        "p95_ms": float(np.percentile(timings, 95)),
        "mean_ms": statistics.fmean(timings),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
