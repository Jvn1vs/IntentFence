from __future__ import annotations

import argparse
import json
from pathlib import Path

from intentfence.route_b_ai_training import build_ai_training_protocol_lock


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Freeze the owner-approved AI-assisted engineering training protocol"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/route_b_ai_training_protocol.yaml"),
    )
    parser.add_argument(
        "--protocol-document",
        type=Path,
        default=Path("docs/route_b_ai_training_protocol.md"),
    )
    parser.add_argument(
        "--integrity-policy",
        type=Path,
        help="Data-construction policy bound to the existing integrity report",
    )
    parser.add_argument(
        "--ai-review-policy",
        type=Path,
        help="Historical AI-review policy used to replay the submitted package",
    )
    parser.add_argument(
        "--confirm-project-owner-approval",
        action="store_true",
        help="Require an explicit owner confirmation before writing the lock",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("configs/route_b_ai_training_protocol_lock.json"),
    )
    args = parser.parse_args()
    if not args.confirm_project_owner_approval:
        parser.error(
            "--confirm-project-owner-approval is required; the lock records a project-owner "
            "protocol amendment"
        )
    if args.output.exists():
        raise FileExistsError(
            f"Refusing to overwrite AI training protocol lock: {args.output}"
        )
    lock = build_ai_training_protocol_lock(
        policy_path=args.config,
        protocol_document=args.protocol_document,
        integrity_policy_path=args.integrity_policy,
        ai_review_policy_path=args.ai_review_policy,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(lock, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(lock, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
