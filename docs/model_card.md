# IntentFence model card

## Status

No trained model or model weight is distributed with this source release. This card is a public
description of the intended model family and the evidence that must accompany a future checkpoint.
Blank performance fields mean `unverified`, not zero and not an achieved target. Engineering smoke
tests must not be presented as model-quality evidence.

## Intended use

Pre-execution risk triage for English-text LLM agents in authorized, sandboxed or production environments that already enforce access control and human confirmation. It may prioritize review or block clearly inconsistent tool proposals.

## Not intended for

Autonomous authorization of payment/deletion/permission changes, safety guarantees, surveillance, unapproved offensive testing, or content moderation unrelated to tool-action consistency.

## Architecture

DeBERTa-v3-small is used for pipeline validation and DeBERTa-v3-base is the candidate main
backbone. A shared encoder feeds a five-class Risk head with labels `benign`,
`instruction_hijacking`, `data_exfiltration`, `privilege_escalation`, and `tool_manipulation`.
The optional Alignment head has two explicitly versioned forms: the legacy binary target
`aligned/conflict`, or the Task Shield-inspired four-label target `aligned`, `unrelated`,
`ambiguous`, `malicious`. The four labels are the project's exact Task Shield label vocabulary;
their use does not claim that the underlying task-alignment idea is novel. Inputs use the
backbone tokenizer's existing separator and the action-aware variant is
`user_goal [SEP] untrusted_content [SEP] proposed_action`.

Risk and Alignment temperatures are fitted separately only after weights freeze, using a disjoint
calibration split. The deployment artifact must record the model revision, label mapping, maximum
length, ONNX variant and SHA-256 hashes before it can be loaded.

## Training data

The current public C1 data card records source revisions, licenses, conversion reports,
deduplication, split manifest hash, class counts, action provenance and the training-readiness
negative findings. It does not constitute a trained-model data release. A future checkpoint card
must additionally record the exact data version, independent human-audit status, class support,
length distribution, hard-negative provenance and all split hashes. Never state that external
detector training membership was independently deduplicated without access to it.

## Evaluation

To be completed only from frozen, hash-bound artifacts: template-held-out Test A, InjecAgent Test B,
NotInject Test C, calibration before/after, a threshold selected at the calibration 1% FPR ceiling,
per-class failures, quantization deltas, hardware, P50/P95, throughput and peak memory. Every
reported number must link to raw predictions or an immutable benchmark report plus its config,
commit and input hashes. No Test A/B/C result is present in this source release.

## Safety and intended decision boundary

This model is a detector/gate, not an authorization system. A low score cannot override
authentication, least privilege, tool-parameter allowlists, sandboxing, audit logs or human
confirmation. Detector failure must follow the tool-specific policy; it must never be converted
into a benign model score.

## Limitations

Prompt-injection defenses can be bypassed adaptively. Performance may degrade on non-English text,
obfuscation, long inputs, missing action context, novel tools and distribution shifts. The C1
legacy Alignment label is deterministically related to Risk; the four-label Route B target still
requires an independent audit before it can support an independent-task claim. Temperature scaling
learned in-domain may remain miscalibrated cross-domain. Explanations, if added, do not establish
causality.
