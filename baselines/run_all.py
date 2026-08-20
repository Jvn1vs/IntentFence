from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from baselines.tfidf import full_probabilities, train  # noqa: E402
from intentfence.constants import RISK_TO_ID  # noqa: E402
from intentfence.inference import RuleBackend  # noqa: E402
from intentfence.metrics import evaluate_risk_predictions  # noqa: E402
from intentfence.schema import read_jsonl  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local core baselines on a frozen split")
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--test", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    train_samples, test_samples = read_jsonl(args.train), read_jsonl(args.test)
    labels = np.array([RISK_TO_ID[sample.risk_label] for sample in test_samples])
    texts = [sample.untrusted_content for sample in test_samples]
    results: dict[str, dict] = {}

    for analyzer in ("word", "char"):
        model = train(train_samples, analyzer)
        results[f"tfidf_{analyzer}"] = evaluate_risk_predictions(
            labels, full_probabilities(model, texts)
        )

    rules = RuleBackend()
    rule_probabilities = np.array(
        [
            [
                rules.predict(s.user_goal, s.untrusted_content, s.proposed_action).probabilities[label]
                for label in RISK_TO_ID
            ]
            for s in test_samples
        ]
    )
    results["rules"] = evaluate_risk_predictions(labels, rule_probabilities)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({name: result["macro_f1"] for name, result in results.items()}, indent=2))


if __name__ == "__main__":
    main()
