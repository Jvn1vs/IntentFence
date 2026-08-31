from __future__ import annotations

import argparse
import json
from pathlib import Path

from intentfence.c2b_authorization import validate_c2b_training_authorization


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a project-owner C2b authorization against frozen Route B evidence"
    )
    parser.add_argument("--authorization-file", type=Path, required=True)
    parser.add_argument("--expected-candidate", required=True)
    parser.add_argument("--candidate-manifest", type=Path, required=True)
    parser.add_argument("--train-path", type=Path, required=True)
    parser.add_argument("--validation-path", type=Path, required=True)
    parser.add_argument("--readiness-report", type=Path, required=True)
    parser.add_argument("--protocol-lock", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--protocol-document", type=Path, required=True)
    parser.add_argument("--integrity-report", type=Path, required=True)
    parser.add_argument("--audit-analysis", type=Path, required=True)
    parser.add_argument("--audit-manifest", type=Path, required=True)
    parser.add_argument("--public-report", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = validate_c2b_training_authorization(
            authorization_path=args.authorization_file,
            expected_candidate=args.expected_candidate,
            candidate_manifest_path=args.candidate_manifest,
            train_path=args.train_path,
            validation_path=args.validation_path,
            readiness_report_path=args.readiness_report,
            protocol_lock_path=args.protocol_lock,
            policy_path=args.policy,
            protocol_document_path=args.protocol_document,
            integrity_report_path=args.integrity_report,
            audit_analysis_path=args.audit_analysis,
            audit_manifest_path=args.audit_manifest,
            public_report_path=args.public_report,
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
