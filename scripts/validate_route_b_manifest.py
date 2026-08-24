from __future__ import annotations

import argparse
from pathlib import Path

from intentfence.route_b_corpus import validate_formal_mock_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay Route B candidate manifest evidence")
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    errors = validate_formal_mock_manifest(args.manifest)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Route B candidate manifest validation passed (training remains blocked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
