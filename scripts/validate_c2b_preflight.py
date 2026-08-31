from __future__ import annotations

import argparse
import json
from pathlib import Path

from intentfence.c2b_authorization import validate_c2b_candidate_inputs


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate C2b candidate train/validation inputs without training authorization"
    )
    parser.add_argument("--expected-candidate", required=True)
    parser.add_argument("--candidate-manifest", type=Path, required=True)
    parser.add_argument("--train-path", type=Path, required=True)
    parser.add_argument("--validation-path", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = validate_c2b_candidate_inputs(
            expected_candidate=args.expected_candidate,
            candidate_manifest_path=args.candidate_manifest,
            train_path=args.train_path,
            validation_path=args.validation_path,
        )
    except (OSError, TypeError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
