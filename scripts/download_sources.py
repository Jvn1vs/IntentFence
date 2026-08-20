from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

SOURCES = {
    "bipia": "https://github.com/microsoft/BIPIA.git",
    "injecagent": "https://github.com/uiuc-kang-lab/InjecAgent.git",
    "notinject": "https://github.com/safolab-wisc/injecguard.git",
    "agentdojo": "https://github.com/ethz-spylab/agentdojo.git",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Clone upstream datasets without modifying them")
    parser.add_argument("sources", nargs="+", choices=tuple(SOURCES))
    parser.add_argument("--destination", type=Path, default=Path("data/raw"))
    args = parser.parse_args()
    args.destination.mkdir(parents=True, exist_ok=True)
    for name in args.sources:
        target = (args.destination / name).resolve()
        if target.exists():
            raise SystemExit(f"Refusing to overwrite existing source directory: {target}")
        subprocess.run(
            ["git", "clone", "--depth", "1", SOURCES[name], str(target)],
            check=True,
        )
        revision = subprocess.run(
            ["git", "-C", str(target), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        print(f"{name}: {revision}")


if __name__ == "__main__":
    main()
