# IntentFence dataset card

No third-party dataset is redistributed in this repository. `data/examples/smoke.jsonl` is a small, synthetic, human-reviewed fixture for tests and demonstrations only. It is not large or diverse enough to support model-quality claims.

## Canonical schema

Every JSONL row contains the user goal, untrusted content, proposed action, five-class risk label, binary alignment label, source/provenance, scenario, severity, template group, split, language, and verification status. Validation is implemented by `IntentSample` in `src/intentfence/schema.py`.

## Public sources

The preparation scripts support locally downloaded copies of BIPIA, InjecAgent and NotInject/InjecGuard. Their upstream licenses and terms remain controlling. Record the upstream commit SHA and retain the original raw data unchanged under ignored `data/raw/` directories.

## Required audit before training

- manually review at least 200 rows stratified by source and risk class;
- mark each row `correct`, `incorrect`, or `ambiguous`;
- exclude ambiguous rows from the main training set;
- document field-boundary loss and rows with `NO_ACTION_PROVIDED`;
- verify that a template group appears in exactly one split;
- publish noise estimates per source and every label correction.

The adapters deliberately set `human_verified=false`. Conversion success does not imply label validity.
