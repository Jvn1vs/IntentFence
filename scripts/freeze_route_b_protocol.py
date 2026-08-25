from __future__ import annotations

import argparse
import json
from pathlib import Path

from intentfence.route_b_readiness import build_route_b_protocol_lock


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seal an owner-approved Route B 2.0.0 protocol"
    )
    parser.add_argument(
        "--config", type=Path, default=Path("configs/route_b_data_protocol.yaml")
    )
    parser.add_argument(
        "--protocol-document",
        type=Path,
        default=Path("docs/route_b_data_protocol.md"),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--confirm-project-owner-approval", action="store_true")
    args = parser.parse_args()
    if not args.confirm_project_owner_approval:
        raise PermissionError(
            "Protocol sealing requires explicit --confirm-project-owner-approval"
        )
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite Route B protocol lock: {args.output}")
    lock = build_route_b_protocol_lock(
        policy_path=args.config,
        protocol_document=args.protocol_document,
    )
    rendered = json.dumps(lock, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
