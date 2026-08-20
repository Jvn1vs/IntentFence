from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _expected_revision() -> str:
    with (ROOT / "configs" / "upstream_sources.yaml").open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)["sources"]["bipia"]["revision"]


def _head(path: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Project-owner wrapper around the pinned official BIPIA builder"
    )
    parser.add_argument("--bipia-root", type=Path, required=True)
    parser.add_argument(
        "--task", choices=("code", "email", "qa", "abstract", "table"), required=True
    )
    parser.add_argument("--contexts", type=Path, required=True)
    parser.add_argument("--attacks", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Generate the export. This data-processing flag is reserved for the project owner.",
    )
    args = parser.parse_args()
    plan = {
        "mode": "execute" if args.execute else "preview_only",
        "bipia_root": str(args.bipia_root.resolve()),
        "expected_revision": _expected_revision(),
        "task": args.task,
        "contexts": str(args.contexts.resolve()),
        "attacks": str(args.attacks.resolve()),
        "output": str(args.output.resolve()),
        "seed": args.seed,
    }
    if not args.execute:
        print(json.dumps(plan, indent=2))
        return
    actual = _head(args.bipia_root)
    if actual != plan["expected_revision"]:
        raise RuntimeError(
            f"BIPIA revision mismatch: expected {plan['expected_revision']}, got {actual}"
        )
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite {args.output}")
    sys.path.insert(0, str(args.bipia_root.resolve()))
    from bipia.data import AutoPIABuilder

    builder = AutoPIABuilder.from_name(args.task)(seed=args.seed)
    frame = builder(str(args.contexts), str(args.attacks))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_json(args.output, orient="records", lines=True, force_ascii=False)
    print(json.dumps({**plan, "rows": len(frame)}, indent=2))


if __name__ == "__main__":
    main()
