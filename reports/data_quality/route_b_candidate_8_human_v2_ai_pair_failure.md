# Route B Candidate 8 人工 v2 包的双 AI 补充审核诊断

## Material Passport

- Origin: Codex dual-model engineering audit
- Date: 2026-08-31
- Verification Status: `ANALYZED`
- Version Label: `candidate_8_human_v2_ai_pair_failure_v1`
- Source: `data/interim/route_b_v2_candidate_8_human_audit_v2_ai_pair/ai_review_analysis.json`
- Source SHA-256: `4d14c4ee51a321891783b7384be89fce78f523ceb259a347e2c0603227ab1b62`
- Audit manifest SHA-256: `34119ebb4e171cc7b9abb1e9230eb6d54cbc5ee240d31a14e14dac79dfcdbe61`
- Evidence boundary: project-owned synthetic corpus; AI engineering evidence only;
  `human_verified=false`; `formal_training_authorized=false`.

## Validation Result

The derived AI-only package was structurally valid: `gpt-5.5` and `gpt-5.4` each completed
400 Risk and 400 Alignment rows, the immutable fields and output hashes were bound, and there
were no package validation errors. The preregistered quality gates nevertheless failed.

| Measure | Result | Gate | Status |
|---|---:|---:|---|
| Risk completion | 1.0000 | >= 0.95 | Pass |
| Risk A/B raw agreement | 0.8000 | >= 0.90 | Fail |
| Risk Cohen's kappa | 0.7500 | >= 0.80 | Fail |
| Risk per-seed-class construct agreement | 0.0000 minimum | >= 0.90 | Fail |
| Alignment completion | 1.0000 | >= 0.95 | Pass |
| Alignment A/B raw agreement | 0.8575 | >= 0.90 | Fail |
| Alignment Cohen's kappa | 0.8100 | >= 0.80 | Pass |
| Alignment per-seed-class construct agreement | 0.5100 minimum | >= 0.90 | Fail |
| Action realism | 0.99875 | >= 0.95 | Pass |

The final analysis status is `ai_quality_gates_failed_engineering_only`. This is not a
classifier-performance result and cannot authorize training.

## Observed Failure Pattern

### Risk taxonomy boundary

Reviewer A emitted the five frozen Risk labels with 80 rows per class and matched the sealed
synthetic class on all 400 sampled rows. Reviewer B also matched the benign, data-exfiltration,
privilege-escalation and tool-manipulation strata, but classified all 80 sampled
`instruction_hijacking` rows as `tool_manipulation`. The only 80 A/B disagreements were therefore
`instruction_hijacking -> tool_manipulation`; reviewer B's construct agreement for that seed class
was 0.0. This is a reproducible model/rubric boundary conflict, not evidence of model accuracy.

### Alignment boundary

Reviewer B matched all four synthetic Alignment strata in this sample. Reviewer A classified 49
seed `unrelated` rows as `malicious`, 6 seed `aligned` rows as `malicious`, and 2 seed `malicious`
rows as `unrelated`. The A/B raw disagreement count was 57/400, with reviewer A's lowest
per-seed-class construct agreement at 0.51 for `unrelated`.

### Action realism

799/800 judgments were `realistic`; one reviewer-B judgment was `unrealistic`. The realism gate
passed, but the single disagreement remains in the raw outputs and was not adjudicated here.

## Integrity and Interpretation

- The two reviewers were distinct local Codex models: OpenAI `gpt-5.5` and `gpt-5.4`, both at
  temperature 0. They saw separate blind sheets and did not receive sealed labels or the other
  reviewer's output.
- The human v2 package was not filled or modified. No human attestation was created, and no AI
  output was applied as `human_verified=true`.
- No labels, thresholds, quality gates, model parameters or training outputs were changed to
  improve agreement. An initial manifest identity mismatch was retained as a local invalid
  analysis artifact; the final manifest passed structural validation.
- Existing candidate 8 AI runs, owner adjudication, sealed labels and the independent-human gate
  remain separate and unchanged.

## Decision

Retain this run as supplementary engineering negative evidence. The candidate remains blocked from
formal training and final-test evaluation until the independent human v2 audit package is completed
and the project owner confirms the next stage. This report does not authorize a new candidate,
label revision, threshold change or training run.
