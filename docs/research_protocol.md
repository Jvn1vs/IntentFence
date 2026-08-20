# IntentFence preregistered research protocol

Protocol version: `1.0.0`  
Prepared: 2026-08-20  
Approval state: **frozen — approved by the project owner on 2026-08-20**

## Material passport

- Origin: Academic Research Suite, deep-research and experiment-agent workflows.
- Evidence cutoff: 2026-08-20.
- Verification status: official publication pages, official repositories, release tags,
  model cards, and dataset cards checked; unresolved claims are labeled explicitly.
- Intended use: a reproducible research artifact and public portfolio project, not a
  production security guarantee.
- Freeze rule: this protocol is approved and immutable for C1 and later stages. Any change
  requires a new protocol version, a written deviation, and a fresh untouched test set.

## Research question brief

### Question

Can a lightweight supervised encoder use the user's goal and a proposed tool action to
detect indirect prompt injection at a calibration-selected low-false-positive operating
point, while being cheaper to run than an online LLM judge?

### FINER assessment

- **Feasible:** BIPIA, InjecAgent, and NotInject are downloadable; the core detector fits a
  single 24 GB GPU. AgentDojo and paid-LLM comparisons remain optional.
- **Interesting:** agent defenses need both attack recall and benign utility; prompt-only
  guards can overreact to suspicious words without testing whether an action conflicts with
  the actual task.
- **Novel:** the claim is deliberately narrow: a lightweight, calibrated, action-aware gate.
  Task/action consistency itself is not claimed as new.
- **Ethical:** all attacks run on offline benchmarks or mock tools. No real message, upload,
  payment, deletion, credential, or third-party service is exercised.
- **Relevant:** the result can be useful even if negative by quantifying when action context,
  hard negatives, or an auxiliary alignment head fail to help.

## Scope and estimands

The unit of prediction is one `(user_goal, untrusted_content, proposed_action)` case. The
primary population is English text with a single structured proposed action. Images,
multi-hour trajectories, adaptive online learning, and a universal safety guarantee are out
of scope.

The deployment estimand is performance at a threshold selected on a disjoint calibration
set. `TPR@1% FPR` means TPR at the calibration-selected threshold whose empirical benign FPR
is at most 1%; the observed test FPR is reported and is allowed to exceed 1% under shift. A
test-set ROC-interpolated `TPR@1% FPR` may be diagnostic only and cannot replace the primary
estimand.

## Frozen inputs

- **A — content only:** `untrusted_content`.
- **B — task aware:** `user_goal [SEP] untrusted_content`.
- **C — action aware:** `user_goal [SEP] untrusted_content [SEP] proposed_action`.

The backbone tokenizer's separator token is used. Truncation budgets and field order are
identical within a comparison and are recorded in the run config.

## Preregistered hypotheses

| ID | Directional hypothesis | Primary comparison | Primary endpoint | Support / failure rule |
|---|---|---|---|---|
| H1 | Task context reduces over-defense. | B vs A, same backbone/data/seed | Difference in NotInject FPR at each model's frozen calibration threshold | Supported only if the paired 95% CI is below 0 and Test A attack TPR is no worse than A by more than 2 percentage points; wrong direction is negative, otherwise inconclusive. |
| H2 | Proposed-action context improves cross-domain attack detection. | C vs B, same backbone/data/seed | Difference in InjecAgent TPR at the frozen threshold | Supported only if the paired 95% CI is above 0; wrong direction is negative, otherwise inconclusive. |
| H3 | Licensed hard benign negatives reduce over-defense without material attack loss. | C with vs without hard negatives | Difference in NotInject FPR | Supported only if the paired 95% CI is below 0 and Test A TPR is no worse by more than 2 points; otherwise negative or inconclusive as above. |
| H4 | The auxiliary alignment task adds information beyond the risk head. | C risk+alignment vs C risk-only | Difference in InjecAgent TPR | Supported only if the paired 95% CI is above 0; a non-improvement removes the auxiliary head from the recommended model. |
| H5 | Post-hoc temperature scaling improves probability reliability. | Frozen C logits after vs before scaling | Difference in Test A risk-head ECE | Supported only if the paired bootstrap 95% CI is below 0 and NLL does not worsen; wrong direction is negative, otherwise inconclusive. |

H6 (cost versus an LLM judge) is exploratory and requires separate approval for local GPU or
paid API use. It cannot rescue a failed H1–H5 result.

## Dataset partition contract

| Role | Permitted use | Planned source |
|---|---|---|
| Train | Gradient updates and hard-negative construction | BIPIA-derived training pool plus separately licensed hard negatives |
| Validation | Hyperparameter and checkpoint selection only | Group-held-out portion of the training sources |
| Calibration | Temperature fitting and threshold selection after weights freeze | Disjoint group-held-out portion of the training sources |
| Test A | Final in-domain generalization | BIPIA held-out templates/groups |
| Test B | Final cross-domain agent attacks | InjecAgent |
| Test C | Final over-defense | NotInject; any added benign set is versioned separately |
| Test D | Optional end-to-end utility/security | AgentDojo `v0.1.35` official task checkers |

No `template_group`, exact duplicate, or detected near-duplicate may cross roles. Source-based
separation takes precedence over target class balance. The adapters may be debugged against
schema-only fixtures, but no model/config/threshold choice may use labels or scores from Test
A–D. The formal tests are run once after model and calibration artifacts are frozen.

## Model and selection rules

- Primary backbone: DeBERTa-v3-base; DeBERTa-v3-small is a pipeline/pilot model.
- Seeds: `42`, `52`, `62`. Seed 42 is permitted for pipeline debugging; all stability claims
  require all three preregistered seeds.
- Shared learning-rate candidates: `1e-5`, `2e-5`, `3e-5`; maximum five epochs.
- Hyperparameter search uses seed 42 and validation only. Select the highest validation risk
  Macro-F1; differences below `0.002` are ties, resolved by the earlier checkpoint and then
  the lower learning rate.
- Once selected, the hyperparameters are shared across A/B/C and ablations. No per-hypothesis
  tuning is allowed.
- Fit risk and alignment temperatures separately on calibration after weights freeze.
- Among calibration thresholds with empirical benign FPR at most 1%, choose the threshold
  with highest attack TPR; break equal-TPR ties with the higher threshold. If none exists,
  record operational failure rather than relaxing the constraint. A maximum calibration TPR
  below 80% at this FPR ceiling is also an operational failure, while results remain reportable.
- External baselines use the same calibration cases when continuous scores exist; their
  upstream default threshold is also reported separately.

## Metrics and statistical analysis

Primary endpoints are fixed in H1–H5. Required diagnostics are observed benign FPR, risk
Macro-F1 and per-class P/R/F1, AUROC, AUPRC, ECE, classwise ECE when sample size permits,
Brier score, NLL, P50/P95 latency, and peak memory.

- Report every seed plus mean and standard deviation; never report only the best seed.
- Use 10,000 paired cluster-bootstrap resamples and percentile 95% confidence intervals.
  Cluster by `template_group` for BIPIA, user-tool/attacker-tool scenario for InjecAgent, and
  trigger-list/category group for NotInject. Seed is an outer stratum for aggregate intervals.
- Confidence intervals and effect sizes are primary. Any secondary null-hypothesis tests use
  Holm correction within a result table and are labeled exploratory.
- At NotInject's 339 cases, one error is about 0.295 percentage points. Report exact counts and
  Wilson intervals; do not claim production-grade 1% FPR precision from this set alone.
- Missing runs, crashes, OOMs, label ambiguities, and null/negative results remain in the run
  ledger. They are not silently dropped.

## Baselines and evidence labels

Required baselines are rules, word TF-IDF, character TF-IDF, the pinned Protect AI detector,
the pinned PIGuard model if runnable under its terms, A, B, and C. Task Shield results are
always labeled exactly `paper-reported`, `reproduced`, or `Task-Shield-inspired approximation`.
No official Task Shield implementation was identified in the paper/repository audit, so its
current status is `paper-reported` only.

External weights may have training overlap with test sources. We record disclosed training
data, publication date, and possible overlap, but do not claim membership-level decontamination
without evidence.

## Resource and provenance contract

- C0–C1: local CPU, no paid service.
- Codex builds and verifies the framework but does not execute any command that updates real
  model weights. It may provide commands, dry-run/static checks, fixtures, and mocked tests.
- The project owner is the sole executor of Small/Base training, tiny-overfit checks, and any
  learned baseline fitting on real project data. User-produced logs may be analyzed afterward.
- C2a: user-operated local CPU/GPU pilot; Codex supplies the reproducible command and checks.
- C2b planning ceiling: user-operated one 24 GB GPU and 60 total GPU-hours. This is a planning
  ceiling, not authorization for Codex to rent hardware or incur any charge.
- Every run records git commit, data/config hashes, seed, OS, CPU/GPU, RAM/VRAM, Python,
  PyTorch/Transformers/CUDA, wall time, GPU-hours, and actual CNY cost.

## Devil's-advocate checkpoint 1

1. Proposed actions may be synthetic or leak labels; C1 must document how each action is
   obtained and audit action realism before H2 is interpretable.
2. The alignment head may merely duplicate the risk label; the contingency table, mutual
   information, and H4 ablation decide whether it survives.
3. NotInject is small and trigger-enriched; it measures over-defense stress, not general benign
   traffic. Claims must stay within that boundary.
4. BIPIA and InjecAgent differ in both domain and construction, so cross-dataset loss cannot be
   attributed to one causal factor.
5. Protect AI and PIGuard disclose broad training mixtures; unknown overlap can bias comparisons.
6. Task Shield, IPIGuard, StruQ, SecAlign, and CaMeL set a novelty ceiling: IntentFence is a
   detector/gate, not a replacement for capability control, structured channels, or information-
   flow enforcement.

These are blocking checks, not discussion notes. C1 cannot exit if action provenance, split
leakage, licensing, or label audit remains unresolved.

## Approval and amendment

The project owner approved this protocol on 2026-08-20. Approval freezes this document,
`docs/baseline_protocol.md`, `docs/threat_model.md`, and
`configs/experiment_registry.yaml` as a coherent protocol. C1 may fill data hashes and measured
counts without changing hypotheses, endpoints, split roles, seeds, or selection rules. Any
substantive amendment increments the protocol version and is disclosed before accessing a new
final test.
