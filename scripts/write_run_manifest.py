from __future__ import annotations

import argparse
import json
from pathlib import Path

from intentfence.run_manifest import build_run_manifest, write_run_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Write an IntentFence run manifest")
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--started-at", required=True)
    parser.add_argument("--ended-at", required=True)
    parser.add_argument("--duration-seconds", type=float, required=True)
    parser.add_argument("--cost-usd", type=float, default=0.0)
    args = parser.parse_args()
    payload = build_run_manifest(
        repository_root=args.repository_root,
        config_path=args.config,
        train_path=args.train,
        validation_path=args.validation,
        checkpoint_dir=args.checkpoint_dir,
        started_at=args.started_at,
        ended_at=args.ended_at,
        duration_seconds=args.duration_seconds,
        cost_usd=args.cost_usd,
    )
    write_run_manifest(payload, args.output)
    print(json.dumps({"status": "run_manifest_written", "output": str(args.output)}))


if __name__ == "__main__":
    main()
