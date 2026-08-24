from __future__ import annotations

import argparse
import json
from pathlib import Path

from intentfence.route_b_corpus import load_mock_corpus_spec, write_formal_mock_corpus


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the authorized offline Route B v2 candidate corpus without training"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/route_b_mock_corpus.yaml"),
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = write_formal_mock_corpus(
        load_mock_corpus_spec(args.config),
        args.output_dir,
        spec_path=args.config,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
