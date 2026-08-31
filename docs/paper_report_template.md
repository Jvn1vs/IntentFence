# IntentFence paper-style report template

Status: `UNVERIFIED` / template plus engineering record only. This document is not a paper result,
does not contain a trained-model conclusion, and must not be submitted until every result cell is
filled from a frozen artifact and passes the integrity checklist.

## Evidence vocabulary

Use one of these labels for every claim: `implemented`, `smoke-tested`, `validated`, `reproduced`,
`paper-reported`, `negative`, `inconclusive`, `unverified`, or `not-run`. Do not use `completed`,
`state of the art`, `safe`, or `improves` without an artifact-backed result and the corresponding
protocol rule.

## Title

**IntentFence: A Calibrated, Action-Aware Gate for Indirect Prompt-Injection Detection**

Provisional title only. The final title must not imply a positive result.

## Abstract (fill only after the evidence gates)

### Background

Indirect prompt injection can cause an agent to treat untrusted content as instructions. IntentFence
tests whether a lightweight encoder can use the user's goal and proposed action at a pre-execution
gate. Task/action consistency is related to prior work and is not claimed as an original idea.

### Methods

The preregistered protocol uses a disjoint train/validation/calibration/Test A/Test B/Test C
partition, a calibration-selected operating threshold, fixed Risk and Alignment labels, and
paired cluster-bootstrap intervals. The primary model, if trained, is a DeBERTa-v3-base encoder;
the deployment path also measures FP32 and dynamic INT8 CPU artifacts.

### Results

`[UNVERIFIED: insert only values present in the claim-evidence matrix, with artifact and config
hashes. If a run was not performed, write "not run" rather than zero.]`

### Conclusion

`[UNVERIFIED: state supported, negative, or inconclusive findings only. Do not infer effectiveness
from framework tests or rule-baseline smoke.]`

## 1. Introduction

### 1.1 Problem

Define the prediction unit as `(user_goal, untrusted_content, proposed_action)` and distinguish
content-only Gate A from action-aware Gate B. State that authorization, least privilege and human
confirmation remain outside the detector.

### 1.2 Related work and novelty boundary

Use `docs/literature_matrix.md` as the source registry. The project contribution is narrowly
framed as a supervised, independently calibrated, CPU-deployable detector/gate comparison. Do not
claim to introduce task/action alignment, structured data channels, or capability control.

### 1.3 Hypotheses

Copy H1-H5 exactly from `docs/research_protocol.md`; do not add post-hoc hypotheses. H6 is optional
and requires separate budget/approval for any local LLM or paid API comparison.

## 2. Materials and methods

### 2.1 Data and licensing

Link the frozen source revisions, licenses, conversion reports, split manifest and label-audit
records from the C1 data card. Describe BIPIA, InjecAgent and NotInject roles separately. State
explicitly that `benchmark_target`, `protocol_wrapper`, and `action_provenance=missing` are not
observed production tool calls.

### 2.2 Split isolation

Report sample IDs/template groups, duplicate and near-duplicate checks, the calibration-only
threshold source and the one-time final-test lock. Any failed or missing gate must remain visible.

### 2.3 Model, calibration and policy

Report model name/revision, input mode, seed, config hash, checkpoint hash, Risk/Alignment label
mapping, temperature values, frozen attack threshold and policy version. State whether Alignment is
legacy binary or the four-label Route B target.

### 2.4 Baselines and metrics

Use rules, word/character TF-IDF, permitted external baselines, and the A/B/C variants only when
their evidence status and terms are recorded. Primary endpoints are TPR@1% FPR and NotInject FPR;
diagnostics include Macro-F1, per-class P/R/F1, AUROC/AUPRC, ECE, classwise ECE, Brier, NLL,
latency, throughput, model size and peak memory.

### 2.5 Statistical analysis

Report each seed, mean/standard deviation, paired cluster-bootstrap percentile 95% intervals,
effect sizes, Wilson intervals for NotInject, and any Holm correction. Never report only the best
seed or tune a threshold on final tests.

### 2.6 Deployment evaluation

Report FP32 versus INT8 on identical frozen inputs and thresholds. Separate cold initialization,
first request, warmed P50/P95, concurrency, process RSS and Python allocation measurements. Do not
call the rules smoke a neural-model latency result.

## 3. Results table (empty until frozen artifacts exist)

| Claim ID | Endpoint / estimate | CI or uncertainty | Evidence artifact | Config / commit | Status |
|---|---|---|---|---|---|
| C1-DATA | `[fill from public data card]` | `[fill or N/A]` | `[path + SHA-256]` | `[manifest/config]` | `validated` / `negative` |
| C2-MODEL | `[not run until owner supplies checkpoint]` | `N/A` | `N/A` | `N/A` | `not-run` |
| C2-CAL | `[not run until owner supplies logits]` | `N/A` | `N/A` | `N/A` | `not-run` |
| C3A-TEST | `[not run; final-test lock]` | `N/A` | `N/A` | `N/A` | `not-run` |
| C3B-DEPLOY | `[rules smoke only; no neural claim]` | `[report path]` | `[smoke report]` | `[commit]` | `smoke-tested` |

Every numeric value added to this table must also appear in `docs/claim_evidence_matrix.md` and
must point to a raw prediction/benchmark artifact, config, commit and input hash. A target, budget,
or planned sample count is not a result.

## 4. Discussion (fill after results)

### 4.1 Findings

`[UNVERIFIED: distinguish supported, negative, and inconclusive hypotheses.]`

### 4.2 Failure analysis

Use sample IDs and non-content metadata for false positives/false negatives. Do not copy private
or untrusted source text into a public report.

### 4.3 Deployment implications

Discuss policy fail-open/fail-closed behavior, calibration drift, CPU cost, model-size trade-offs
and the fact that the detector does not authorize actions.

## 5. Limitations, ethics and data availability

Include the limitations in `docs/threat_model.md`, the C1 data card's label/provenance limits,
unknown external-detector training overlap, English-only scope, adaptive bypass risk, and the fact
that NotInject is a small trigger-enriched stress set. State that demonstrations use mock tools and
do not send, upload, delete, pay or change permissions.

Data availability must state whether a source artifact is redistributed, linked, or only described;
follow each upstream license. Do not publish raw third-party data, credentials, personal data,
checkpoints or ignored result caches.

## 6. AI-use and author statements

Use `docs/ai_usage_disclosure.md`, the CRediT statement, funding statement, conflict-of-interest
statement and ethics declaration. AI assistance does not count as independent human label review;
the project owner remains responsible for training, calibration, final-test authorization and
publication approval.

## Appendix: reproducibility handoff

Attach the completed `docs/reproducibility_checklist.md`, claim-evidence matrix, experiment log,
run manifests, source/license manifest, model/calibration/export hashes and raw predictions only
in a controlled artifact location. The public repository should contain links or public aggregate
reports only when their release is approved.
