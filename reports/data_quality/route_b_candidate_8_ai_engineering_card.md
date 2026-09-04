# Route B candidate 8 AI engineering evidence card

Status: `AI_ENGINEERING_EVIDENCE_STRUCTURALLY_BOUND_QUALITY_GATES_FAILED`

## Material Passport

- Route: `B-ai-assisted-engineering`
- Protocol: `2.2.0-ai-assisted-engineering.1`
- Source: project-owned offline mock-tool scenarios only
- Candidate manifest sealed SHA-256: `64c99b8e966020808470b732ed7e73ca26a8ca121220f188d0a825320302e585`
- AI evidence: OpenAI `gpt-5.5` and `gpt-5.4`, local execution, temperature `0`
- Evidence class: `ai_reviewed_engineering_only`

## Evidence boundary

The candidate contains 27,000 project-owned synthetic rows across train, validation, calibration
and Test A. The data manifest, action traces, split isolation report and the label-neutral
dual-AI package are preserved in the ignored local evidence directories. This card is an
aggregate pointer only; it does not contain raw third-party data, reviewer notes or sealed labels.

## AI review result

Both AI reviewers completed 400 Risk and 400 Alignment/action rows. The package structure,
immutable fields, reviewer separation and output hashes passed deterministic validation.
Pre-registered quality gates did not all pass:

| Measure | Result | Gate |
|---|---:|---:|
| Risk raw inter-reviewer agreement | 0.8000 | >= 0.90 |
| Risk Cohen's kappa | 0.7500 | >= 0.80 |
| Risk minimum per-class construct agreement | 0.0000 | >= 0.90 |
| Alignment raw inter-reviewer agreement | 0.8575 | >= 0.90 |
| Alignment Cohen's kappa | 0.8100 | >= 0.80 |
| Alignment minimum per-class construct agreement | 0.5100 | >= 0.90 |
| Action realism | 0.99875 | >= 0.95 |

The recorded analysis status is `ai_quality_gates_failed_engineering_only`. The failure is
preserved and is not repaired by changing labels, thresholds or source files. The route can
proceed only to the owner-risk-acceptance step for engineering-only training.

## Claims and locks

`human_verified=false` and `formal_training_authorized=false` remain in force. This card is
not evidence of independent human validation, ground-truth accuracy, calibration, final-test
performance or publication readiness. The project owner remains the sole training executor;
calibration and Test A/B/C/D remain locked.
