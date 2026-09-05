from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Allow ``python baselines/predict.py`` from the repository root as well as
# the preferred ``python -m baselines.predict`` form.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import joblib

from baselines.piguard import PIGuardBaseline
from baselines.protectai import ProtectAIBaseline
from baselines.tfidf import full_probabilities
from intentfence.constants import RISK_LABELS
from intentfence.inference import RuleBackend
from intentfence.schema import IntentSample, read_jsonl


def _records_from_scores(
    samples: list[IntentSample], scores: list[float], backend: str, revision: str
) -> list[dict[str, Any]]:
    return [
        {
            "sample_id": sample.sample_id,
            "split": sample.split,
            "source": sample.source,
            "attack_label": sample.attack_label,
            "risk_label": sample.risk_label,
            "attack_score": float(score),
            "backend": backend,
            "revision": revision,
        }
        for sample, score in zip(samples, scores, strict=True)
    ]


def predict_rules(samples: list[IntentSample]) -> list[dict[str, Any]]:
    backend = RuleBackend()
    scores = [
        1.0
        - backend.predict(
            sample.user_goal, sample.untrusted_content, sample.proposed_action
        ).probabilities["benign"]
        for sample in samples
    ]
    return _records_from_scores(samples, scores, "rules", "repository_rules")


def predict_tfidf(samples: list[IntentSample], model_path: Path) -> list[dict[str, Any]]:
    model = joblib.load(model_path)
    probabilities = full_probabilities(model, [sample.untrusted_content for sample in samples])
    benign_index = RISK_LABELS.index("benign")
    return _records_from_scores(
        samples,
        (1.0 - probabilities[:, benign_index]).tolist(),
        "tfidf",
        model_path.name,
    )


def predict_external(
    samples: list[IntentSample], backend_name: str, model_id: str, revision: str, device: int
) -> list[dict[str, Any]]:
    if backend_name == "protectai":
        backend = ProtectAIBaseline(device=device, revision=revision)
    else:
        backend = PIGuardBaseline(model_name=model_id, revision=revision, device=device)
    scores = backend.attack_scores([sample.untrusted_content for sample in samples])
    return _records_from_scores(samples, scores, backend_name, revision)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Project-owner baseline prediction; writes scores without test-set tuning"
    )
    parser.add_argument(
        "--backend", choices=("rules", "tfidf", "protectai", "piguard"), required=True
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", type=Path, help="Required for TF-IDF")
    parser.add_argument("--model-id", help="Required for external models")
    parser.add_argument("--revision", help="Required for external models")
    parser.add_argument("--device", type=int, default=-1)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite {args.output}")
    samples = read_jsonl(args.input)
    if args.backend == "rules":
        records = predict_rules(samples)
    elif args.backend == "tfidf":
        if args.model is None:
            parser.error("--backend tfidf requires --model")
        records = predict_tfidf(samples, args.model)
    else:
        if not args.model_id or not args.revision:
            parser.error("external backends require --model-id and immutable --revision")
        records = predict_external(samples, args.backend, args.model_id, args.revision, args.device)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records
        ),
        encoding="utf-8",
    )
    print(json.dumps({"backend": args.backend, "rows": len(records)}, indent=2))


if __name__ == "__main__":
    main()
