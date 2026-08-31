# Route B Candidate 6 双 AI 审核失败诊断

## Material Passport

- Origin Skill: Academic Research Suite / experiment-agent
- Origin Mode: validate
- Origin Date: 2026-08-30
- Verification Status: ANALYZED
- Version Label: `candidate_6_ai_audit_failure_v1`
- Source: `data/interim/route_b_v2_candidate_6_audit_v2/ai_review_analysis.json`
- Source SHA-256: `fa3ddee65c8e9398af97a6edb1f9f0b056d50e175df213194bc67e393e7b0850`
- Evidence boundary: synthetic project-owned corpus; AI engineering evidence only;
  `human_verified=false`; `formal_training_authorized=false`.

## Validation Result

The dual-AI package is structurally valid: both reviewers completed 400 Risk and 400
Alignment rows, all immutable fields and output hashes validated, and no package validation
error occurred. The preregistered quality gates nevertheless failed.

| Measure | Result | Gate | Status |
|---|---:|---:|---|
| Risk completion | 1.0000 | >= 0.95 | Pass |
| Risk A/B raw agreement | 0.8925 | >= 0.90 | Fail |
| Risk Cohen's kappa | 0.8499 | >= 0.80 | Pass |
| Risk per-seed-class construct agreement | below 0.90 in multiple classes | >= 0.90 | Fail |
| Alignment completion | 1.0000 | >= 0.95 | Pass |
| Alignment A/B raw agreement / kappa | 1.0000 / 1.0000 | >= 0.90 / >= 0.80 | Pass |
| Alignment per-seed-class construct agreement | `ambiguous` = 0.0000 for both | >= 0.90 | Fail |
| Action realism | 1.0000 | >= 0.95 | Pass |

The final analysis status is `ai_quality_gates_failed_engineering_only`. This is not a
classifier-performance result and cannot authorize training.

## Failure Pattern

### Risk-label construct mismatch

Both reviewers applied the frozen Risk rubric's “primary attack purpose” ordering. Under that
ordering, all 80 seed `instruction_hijacking` rows were classified as a more specific effect:
53 as `data_exfiltration`, 9 as `privilege_escalation`, and 18 as `tool_manipulation`.
Neither reviewer emitted `instruction_hijacking` for this seed class.

The seed `tool_manipulation` class also overlaps the rubric's higher-priority effects. Reviewer
A agreed with that seed label on 19/80 rows; reviewer B on 42/80. The remainder was primarily
classified as data exfiltration or privilege escalation. This explains both the construct-agreement
failure and 43 A/B Risk disagreements: 23 `data_exfiltration -> tool_manipulation` and 20
`data_exfiltration -> benign` transitions from A to B.

### Alignment-label construct mismatch

The two reviewers agreed on every Alignment row, but both classified all 100 seed `ambiguous`
rows as `unrelated`. The generated actions therefore present enough information to determine that
they do not serve the user goal; they do not meet the rubric's definition of an authorization-
uncertain action. This is a dataset-construct problem, not an inter-reviewer inconsistency.

## Integrity and Interpretation Scan

| Check | Status | Finding |
|---|---|---|
| Package blinding | Pass for `audit_v2` | Reviewer-facing IDs are label-neutral; invalid `audit_v1` was not used. |
| Completion denominator | Pass | Every metric uses the fixed 400-row audit denominator. |
| Post-hoc threshold/model selection | Pass | The failed result is retained; no substitute B output or threshold change was used. |
| Reviewer independence | Caution | Models differ (`gpt-5.6-sol`, `gpt-5.6-terra`) but share a provider and may share modeling biases. |
| Construct validity | Red flag | Seed labels conflict systematically with the frozen semantic decision rules. |
| External validity | Not assessed | This is project-owned synthetic data, not Test B/C/D evaluation. |
| Inferential claims | Not applicable | No hypothesis test, confidence interval, or model-performance claim is made. |

## Allowed Next Design Work

No change may be applied to candidate 6 labels, quality gates, reviewer outputs, or its failed
status. If a future candidate is authorized, its protocol should first resolve the observed
construct conflict prospectively:

1. Make `instruction_hijacking` rows request only control-flow override without a primary
   exfiltration, privilege, or tool-manipulation effect; or revise the Risk taxonomy and rubric
   together before construction.
2. Make `ambiguous` Alignment rows genuinely authorization-underdetermined, rather than plainly
   unrelated to the stated task.
3. Pre-register any new candidate, audit sample, reviewer identities, and quality gates before
   generating new reviewer outputs.

This report does not authorize those changes or any training run.
