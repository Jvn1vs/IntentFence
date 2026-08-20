.PHONY: install test lint smoke api baseline

install:
	python -m pip install -e ".[dev]"

test:
	python -m pytest

lint:
	python -m ruff check .

smoke:
	python scripts/build_splits.py --input data/examples/smoke.jsonl --output-dir data/processed/smoke

api:
	intentfence-api

baseline:
	python baselines/run_all.py --train data/examples/smoke.jsonl --test data/examples/smoke.jsonl --output reports/tables/smoke_baselines.json
