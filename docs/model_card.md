# IntentFence model card

## Status

No trained model is distributed with this source release. This card defines the information required when a checkpoint is published; blank performance fields must not be interpreted as zero or as achieved targets.

## Intended use

Pre-execution risk triage for English-text LLM agents in authorized, sandboxed or production environments that already enforce access control and human confirmation. It may prioritize review or block clearly inconsistent tool proposals.

## Not intended for

Autonomous authorization of payment/deletion/permission changes, safety guarantees, surveillance, unapproved offensive testing, or content moderation unrelated to tool-action consistency.

## Architecture

DeBERTa-v3-small for pipeline validation and DeBERTa-v3-base for the candidate main model. A shared encoder feeds a five-class risk head and a binary alignment head. Inputs are separated with the tokenizer's existing separator. Temperatures for the heads are fitted separately after weights freeze.

## Training data

To be completed with source versions, licenses, conversion reports, deduplication, split manifest hash, manual audit/noise rates, class counts, lengths, languages and hard-negative provenance. Never state that external detector training membership was independently deduplicated without access to it.

## Evaluation

To be completed with template-held-out, InjecAgent cross-dataset and NotInject results; calibration before/after; threshold chosen at 1% FPR; per-class failures; quantization deltas; hardware and P50/P95. Link raw predictions and configs.

## Limitations

Prompt-injection defenses can be bypassed adaptively. Performance may degrade on non-English text, obfuscation, long inputs, missing action context, novel tools and distribution shifts. Alignment labels are redundant with risk in the initial schema. Temperature scaling learned in-domain may remain miscalibrated cross-domain. Explanations, if added, do not establish causality.
