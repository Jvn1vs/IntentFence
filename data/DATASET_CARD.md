# IntentFence dataset card

No third-party dataset is redistributed in this repository. `data/examples/smoke.jsonl` is a small, synthetic, human-reviewed fixture for tests and demonstrations only. It is not large or diverse enough to support model-quality claims.

## Canonical schema

This card describes the public C1/smoke legacy schema. Every row contains the user goal, untrusted
content, proposed action, five-class risk label, binary alignment label, source/provenance,
scenario, severity, template group, split, language, and verification status. Route B v2 uses a
separate four-label `task_alignment_label` field (`aligned`, `unrelated`, `ambiguous`, `malicious`)
and must not be silently mixed with this snapshot. Validation is implemented by `IntentSample` in
`src/intentfence/schema.py`.

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

The real-data workflow is project-owner-authorized: Codex may execute the pinned download,
conversion, merge, deduplication, split construction, quality inspection, label-audit pre-review
and reproducibility-report steps recorded in the repository. The project owner remains the
independent human sign-off authority and sole executor of training-related work; each run must
record the actual executor, source hashes, license terms and review status in its manifest.
