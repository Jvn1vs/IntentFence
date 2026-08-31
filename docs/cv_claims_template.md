# Resume and project-description claim template

Status: do not copy the result placeholders into a resume until the linked evidence is complete.

## Safe engineering-only wording available now

- Implemented a reproducible, hash-bound framework for indirect prompt-injection data validation,
  calibration gates, fixed-threshold evaluation, ONNX/INT8 export checks and FastAPI policy failure
  handling; verified with static checks and synthetic fixtures.
- Added an action-aware inference interface that exposes model/calibration/policy provenance and
  keeps read-only detector failure separate from fail-closed communication/sensitive actions.

These bullets describe implementation, not effectiveness, accuracy or safety guarantees.

## Result-based bullet (fill only after C2/C3 evidence)

`[Model/config] achieved [verified endpoint] on [split] at [fixed threshold], with [CI/uncertainty],
under [hardware/runtime]; evidence: [predictions/report path + SHA-256], [config/hash], [commit].`

## Deployment bullet (fill only after real model measurement)

`[Frozen revision] ran at [P50/P95] with [throughput] and [peak RSS/model size] on [CPU/runtime],
comparing [FP32/INT8] on the same frozen inputs; evidence: [latency report + SHA-256].`

## Prohibited wording until evidence exists

- “improves security”, “beats SOTA”, “safe”, “production-ready” or “prevents prompt injection”;
- any Accuracy/F1/TPR/FPR/ECE/P50/P95 number not linked to an immutable artifact;
- a claim that Task Shield or task/action alignment was first introduced by IntentFence;
- a claim that synthetic benchmark actions are observed real Agent actions.
