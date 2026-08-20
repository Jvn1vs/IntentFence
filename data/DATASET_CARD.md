# IntentFence dataset card

No third-party dataset is redistributed in this repository. `data/examples/smoke.jsonl` is a small, synthetic, human-reviewed fixture for tests and demonstrations only. It is not large or diverse enough to support model-quality claims.

## Canonical schema

Every JSONL row contains the user goal, untrusted content, proposed action, five-class risk label, binary alignment label, source/provenance, scenario, severity, template group, split, language, and verification status. Validation is implemented by `IntentSample` in `src/intentfence/schema.py`.

## Public sources and strict adapters

The project-owner preparation flow supports pinned BIPIA, InjecAgent and NotInject artifacts. Their upstream licenses and terms remain controlling. `scripts/download_sources.py` is preview-only unless the project owner supplies both execution and license-acknowledgement flags. Raw artifacts and manifests remain under ignored `data/raw/` directories.

Adapters use named, strict profiles rather than guessing among loosely related fields:

- `bipia_generated_v1` / `bipia_clean_v1`;
- `injecagent_direct_harm_v1` / `injecagent_data_stealing_v1`;
- `notinject_v1`.

Every converted row records adapter, label and action provenance. Missing BIPIA actions, InjecAgent benchmark-target actions and the NotInject protocol wrapper are materially different evidence and must not be pooled without disclosure.

## Required audit before training

- manually review at least 200 rows stratified by source and risk class;
- mark each row `correct`, `incorrect`, or `ambiguous`;
- exclude ambiguous rows from the main training set;
- document field-boundary loss and rows with `action_provenance=missing`;
- verify that a template group appears in exactly one split;
- publish noise estimates per source and every label correction.

The adapters deliberately set `human_verified=false`. Conversion success does not imply label validity.

Real dataset download, conversion, merging, splitting and auditing are executed by the project owner. Codex only maintains the framework and synthetic fixture tests.
