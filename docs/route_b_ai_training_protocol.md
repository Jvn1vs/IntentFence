# Route B AI-assisted engineering training protocol

## Material Passport

- Protocol version: `2.2.0-ai-assisted-engineering.1`
- Status: `frozen`
- Amendment date: `2026-09-04`
- Route: `B-ai-assisted-engineering`
- Evidence class: `ai_reviewed_engineering_only`
- Parent records: Route B `2.0.0-draft.2` and dual-AI review `2.1.0-ai-draft.1`

This is an explicit training-route amendment. It does not rewrite the historical human-review
route, the candidate data, the sealed labels, or any prior AI result.

## 1. What AI may do

Two distinct AI reviewer identities may independently review the same blinded package:

- 400 Risk rows using the frozen five labels;
- 400 Alignment/action rows using `aligned`, `unrelated`, `ambiguous`, and `malicious`;
- action realism for Alignment rows;
- temperature `0`, hidden seed labels, hidden other-reviewer output, and preserved raw CSVs;
- provider, model, revision, prompt hash, execution mode, and output hashes recorded in the
  AI manifest.

The two reviewers are a consistency pair, not two human reviewers. Agreement with the sealed
synthetic construction is reported only as `construct_agreement`. AI output must never be
written as `human_verified=true`.

## 2. What this route authorizes

After the structural evidence is bound, the route may open an
`eligible_for_owner_ai_engineering_authorization` readiness state. The project owner may then
create a separate authorization file for an exploratory engineering run. The owner remains the
training executor.

This route can support:

- engineering training and debugging;
- checking the train/validation input contract and checkpoint plumbing;
- reproducibility and pipeline demonstrations.

It cannot support paper-grade label-quality claims, independent human validation claims, or
formal performance claims.

## 3. Failed AI quality gates

The pre-registered thresholds are unchanged:

- completion at least `0.95`;
- raw inter-reviewer agreement at least `0.90`;
- Cohen's kappa at least `0.80`;
- every seed-class agreement at least `0.90`;
- realistic action fraction at least `0.95`.

Failure is preserved; labels, thresholds, reviewer sheets, and historical analyses are not
edited to manufacture a pass. If the structural evidence is otherwise valid, the owner may
explicitly accept the failed AI quality gates for engineering-only training by recording a
reason in the authorization file. Without that reason, the run is rejected.

For the current candidate 8 `gpt-5.5`/`gpt-5.4` package, Risk agreement is `0.80` with
kappa `0.75`, Alignment agreement is `0.8575` with kappa `0.81`, and the lowest per-class
agreements are `0` and `0.51`. Therefore the package is valid engineering evidence but
requires explicit owner risk acceptance before any owner-run engineering training.

## 4. Locks that remain in force

`human_verified=false` and `formal_training_authorized=false` remain mandatory in the policy,
protocol lock, readiness report, AI manifest, and AI analysis. This route does not unlock:

- calibration or threshold fitting;
- Test A/B/C/D or any final-test evaluation;
- publication or paper-grade conclusions;
- paid APIs, rented GPU capacity, or model/data downloads.

Any later calibration or final-test stage requires its own owner authorization and frozen
evidence. The historical human-review route remains available if formal evidence is needed.

## 5. Required evidence bindings

The AI readiness report binds the new training protocol, its protocol lock, the original data
integrity policy and report, the candidate manifest, the public aggregate card, the AI review
policy, the AI review manifest, the AI review analysis, and the AI audit manifest. The validator
replays the candidate/integrity checks and the dual-AI analysis before accepting an authorization.

Use the separate AI route files; do not pass the unfinished human v2 package as an AI manifest or
overwrite either package.
