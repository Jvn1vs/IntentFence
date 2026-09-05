.PHONY: install test lint smoke api baseline public-audit release-readiness

install:
	python -m pip install -e ".[dev]" --index-url https://pypi.org/simple

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

public-audit:
	python scripts/audit_public_release.py --include-untracked

release-readiness:
	python scripts/check_release_readiness.py --ref HEAD
