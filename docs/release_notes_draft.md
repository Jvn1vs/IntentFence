# IntentFence 0.1.0 — release notes draft

Status: **DRAFT — not approved for merge or public release**.

This is a source-only engineering snapshot. It does not distribute a trained checkpoint, real
calibration artifact, final-test prediction, third-party raw dataset, or model-quality result.
Project-owner approval is still required before this document is used as release material.

## Included in this snapshot

- A typed canonical schema with source/provenance fields, exact and near-duplicate checks, and
  template-group-aware split contracts.
- Rules, word-level TF-IDF and character-level TF-IDF baseline interfaces, plus a versioned
  multitask model/training contract. This source snapshot contains no owner-run or Codex-run
  learned baseline, checkpoint, real calibration artifact or performance result.
- Future-facing Risk and Alignment calibration contracts, fixed calibration-only threshold rules,
  and fail-closed provenance checks for calibration and formal Test A/B/C access. The current
  public snapshot does not validate an independently audited Alignment target.
- FastAPI `/health`, `/v1/evaluate` and `/demo` endpoints with tool-specific failure handling;
  a local Uvicorn rules-only smoke passed, while demonstrations use rules or mocks and do not
  perform real tool actions.
- PyTorch/ONNX export contracts, dynamic INT8 metadata checks, CPU benchmark tooling, and a
  scripted Docker rules-backend smoke path. Fixture/static deployment-contract checks pass, and one
  actual rules-only container runtime smoke passed; no model/ONNX/INT8 result is implied.
- Reproducibility, threat-model, model-card, data-card, AI-use and claim-evidence documentation
  that keeps missing experiments and negative data-readiness findings explicit.

## Evidence and limitations

- The public source tree contains no trained model weights or real Test A/B/C result.
- Synthetic fixtures, rules-only smoke and static checks demonstrate framework behavior only; they
  do not establish detection accuracy, safety, latency, quantization quality or generalization.
- The current Route B candidate 8 AI reviews, project-owner adjudication package and supplemental
  AI checks are engineering evidence only. The required two-independent-human v2 audit remains
  incomplete; `human_verified=false` and `formal_training_authorized=false` remain unchanged.
- No real logits export, temperature fitting or threshold freeze has been run; calibration remains
  a separate owner-approved gate.
- Training, learned-parameter fitting, formal final-test evaluation and publication approval remain
  project-owner responsibilities and gates. The independent human audit is a training-entry gate.
- The detector is not an authorization, least-privilege or human-confirmation replacement, and
  adaptive attacks or distribution shifts may bypass it.

## Before any release

The project owner must review the exact committed tree, source licenses and attribution, all
quantitative claims, the independent human-audit state, and the final public wording. A future
model release also requires hash-bound checkpoint, calibration, prediction, deployment and
reproducibility artifacts; those artifacts must remain outside the public source tree unless their
licenses and release scope are separately approved. The automated public-release audit, committed-
tree readiness check, CI gates, and manual tracked-file/license review must pass on the exact release
commit.
