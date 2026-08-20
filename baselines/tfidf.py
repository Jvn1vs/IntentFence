from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from intentfence.constants import RISK_LABELS
from intentfence.schema import IntentSample, read_jsonl


def build_pipeline(analyzer: str) -> Pipeline:
    if analyzer == "word":
        vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1, max_features=50_000)
    elif analyzer == "char":
        vectorizer = TfidfVectorizer(
            analyzer="char_wb", ngram_range=(3, 5), min_df=1, max_features=80_000
        )
    else:
        raise ValueError("analyzer must be word or char")
    classifier = LogisticRegression(
        max_iter=1_000,
        class_weight="balanced",
        random_state=42,
    )
    return Pipeline((("tfidf", vectorizer), ("classifier", classifier)))


def train(samples: list[IntentSample], analyzer: str) -> Pipeline:
    if len({sample.risk_label for sample in samples}) < 2:
        raise ValueError("TF-IDF training needs at least two risk classes")
    model = build_pipeline(analyzer)
    model.fit([sample.untrusted_content for sample in samples], [sample.risk_label for sample in samples])
    return model


def full_probabilities(model: Pipeline, texts: list[str]) -> np.ndarray:
    partial = model.predict_proba(texts)
    classes = list(model.named_steps["classifier"].classes_)
    output = np.zeros((len(texts), len(RISK_LABELS)), dtype=float)
    for index, label in enumerate(RISK_LABELS):
        if label in classes:
            output[:, index] = partial[:, classes.index(label)]
    row_sums = output.sum(axis=1, keepdims=True)
    return np.divide(output, row_sums, out=np.zeros_like(output), where=row_sums != 0)


def save_model(model: Pipeline, output: Path, metadata: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, output)
    output.with_suffix(".json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a TF-IDF + logistic regression baseline")
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--analyzer", choices=("word", "char"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    samples = read_jsonl(args.train)
    model = train(samples, args.analyzer)
    save_model(model, args.output, {"analyzer": args.analyzer, "samples": len(samples), "seed": 42})


if __name__ == "__main__":
    main()
