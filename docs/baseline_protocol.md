# Frozen baseline and evaluation protocol

Protocol version: 1.0.0 (frozen by project-owner approval on 2026-08-20)

The normative hypothesis, statistics, selection, and amendment rules are in
`docs/research_protocol.md` and `configs/experiment_registry.yaml`. This file is the concise
baseline-facing view of the same protocol.

## Claim boundary

IntentFence does not claim to originate task/action consistency checking. Its testable contribution is a supervised, lightweight and independently calibrated encoder that can reduce online judge cost and deployment dependencies. A useful result may be higher recall at fixed FPR, better hard-negative generalization, comparable safety at lower latency, or a documented negative result.

## Frozen inputs

- Model A: `untrusted_content` only.
- Model B: `user_goal [SEP] untrusted_content`.
- Model C: `user_goal [SEP] untrusted_content [SEP] proposed_action`.

Use a backbone's existing separator token. Added structural tokens require a separate same-data/same-seed ablation.

## Dataset roles

- training pool: BIPIA-derived rows plus self-built, licensed hard negatives;
- validation: model/config selection only;
- calibration: temperature and decision thresholds after weights freeze;
- test A: BIPIA source with held-out templates;
- test B: InjecAgent cross-dataset;
- test C: NotInject/hard-negative over-defense;
- test D: optional AgentDojo unseen-tool/system evaluation.

A `template_group` and its near duplicates must stay in one partition. The source commit, conversion report, manual audit, split manifest and hashes are immutable inputs to a final run.

## Required baselines

1. transparent keyword/regex rules;
2. word TF-IDF + logistic regression;
3. character TF-IDF + logistic regression;
4. ProtectAI `deberta-v3-base-prompt-injection-v2` at a pinned revision;
5. PIGuard/InjecGuard at a pinned revision;
6. same-backbone IntentFence single-text model;
7. full action-aware IntentFence model.

External weights are evaluated on the same frozen tests, but training-membership deduplication is not claimed. Record model-card training disclosures, publication date and possible contamination.

## Threshold rules

- Never choose a threshold on a final test.
- Report the upstream default threshold where one exists.
- Choose IntentFence's operating threshold only on the calibration split.
- Select the deployment threshold on calibration only by maximizing attack TPR subject to
  empirical benign FPR no greater than 1%. Primary test TPR and FPR use that frozen threshold;
  a test-ROC-interpolated `TPR@1% FPR` is diagnostic only.
- Report NotInject FPR and exact false-positive categories.
- Fit risk and alignment temperatures separately.

## Metrics

Deployment constraints precede optimization: benign FPR, allowed utility loss, cross-domain stability and P95 CPU latency. H1-H5 each have a single primary endpoint in the research protocol. Required diagnostics are Macro-F1, per-class precision/recall/F1, AUROC, AUPRC, test-ROC `TPR@1% FPR`, ECE, classwise ECE where supported, Brier and NLL.

AgentDojo is optional. It must use a pinned benchmark/task suite and the official task utility checkers for Benign Utility and Utility Under Attack, alongside Targeted ASR. Do not replace those checks with a generic LLM judge.

## Task Shield labels

Any Task Shield comparison is exactly one of `paper-reported`, `reproduced`, or `Task-Shield-inspired approximation`. The last category cannot be compared as a direct numerical reproduction.

## Result acceptance

A result table is publishable only when it links to raw predictions, immutable configs, manifest hash, calibration artifact, commit, seed and hardware. One seed is explicitly labeled; stability claims require repeated seeds. Quantized models must rerun security metrics, not just latency.
