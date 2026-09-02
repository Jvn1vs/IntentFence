# Claim–evidence matrix

This is the publication gate for quantitative and novelty claims. A row marked `unverified`,
`not-run`, or `negative` cannot be rewritten as a positive result. Every number in the paper,
README or resume material must map to one row and to an immutable artifact.

| ID | Provisional claim | Evidence required | Current evidence | Status | Publication rule |
|---|---|---|---|---|---|
| C0-PROTOCOL | The estimands, splits, hypotheses and final-test lock are frozen. | `docs/research_protocol.md`, `configs/experiment_registry.yaml`, protocol validators. | Frozen protocol and registry are present; this is a design fact, not an effectiveness result. | `validated` | May describe the protocol; do not call it a result. |
| C1-DATA | The C1 source/conversion/split evidence chain is reproducible under its recorded licenses. | Source manifest, conversion reports, deduplication/split reports, data-card hashes. | Public aggregate data card and task plan record the C1 evidence and its training-readiness failures. | `validated` / `negative` | Report the exact snapshot and limits; do not imply a released dataset or trained model. |
| C1-READINESS | The current C1 snapshot is not ready for the original five-class/action/independent-Alignment training claim. | `docs/training_entry_decision.md`, readiness report, manifest. | The entry decision records missing class support, action provenance and label redundancy. | `validated` / `negative` | This negative finding must remain visible. |
| C2-MODEL | A supervised model improves an endpoint over a baseline. | Owner-run checkpoint, run manifest, fixed predictions, config and seed summary. | No checkpoint or real model result is present in this source release. | `not-run` | Do not write a performance number or “improves”. |
| C2-CAL | Temperature scaling improves reliability or freezes an operational threshold. | Calibration logits sidecar, calibration artifact/report, owner authorization and hashes. | Calibration framework exists; no real logits, temperatures or threshold. | `not-run` | Do not report ECE/Brier/NLL or a threshold. |
| C3A-TEST | The candidate generalizes on Test A/B/C or changes false-positive behavior. | One-time final-test ledger, raw predictions, fixed-threshold analysis and CI. | Final-test lock remains unused; no Test A/B/C predictions were read or produced. | `not-run` | Do not form a paper conclusion or resume metric. |
| C3B-API | The service exposes version metadata and applies tool-specific failure policy. | TestClient fixture, API schema and policy tests; one scripted local Uvicorn rules-only smoke. | Rules/mock tests and the 2026-09-02 scripted local Uvicorn smoke cover application/model version fields, `/health`, external-communication blocking and read fail-open/external fail-closed. | `smoke-tested` | May be described as engineering behavior, not model safety. |
| C3B-DEPLOY | The ONNX/INT8 artifact contract rejects unbound or tampered files. | Fixture export metadata, file/tokenizer hashes and validator tests. | C3b fixture tests pass; no real ONNX or INT8 artifact exists. | `smoke-tested` | May describe the implementation; no quantization quality claim. |
| C3B-LATENCY | The model has a measured CPU P50/P95, throughput and memory profile. | Owner-run FP32/INT8 reports with model/config hashes and matching inputs. | Rules-only CLI smoke proves the benchmark tool; no neural model measurement exists. | `not-run` | Never reuse rules numbers as model numbers. |
| NOVELTY-BOUNDARY | IntentFence does not claim to originate task/action alignment or capability control. | `docs/literature_matrix.md`, protocol and threat model. | Existing-work boundary is explicitly documented. | `validated` | Preserve this wording in paper and resume. |
| RELEASE-SAFETY | Public source excludes raw data, credentials, checkpoints and ignored caches. | `scripts/audit_public_release.py`, `scripts/check_release_readiness.py`, Git tracked-file review and license checklist; `.dockerignore`, `deployment/Dockerfile` and `scripts/run_c3b_docker_smoke.ps1` are supplementary Docker build-context/runtime evidence. | Automated source audit and committed-tree preflight are the C4 public-source evidence; one rules-only Docker container runtime smoke also passed. Final public approval remains pending. | `smoke-tested` | Do not publish until the audit and owner approval pass. |

## Required artifact tuple for a future result

`{claim_id, estimate, uncertainty, split, threshold_source, artifact_path, artifact_sha256,
config_path, config_sha256, git_commit, seed, environment, executor, cost, deviations}`

If any required member is unavailable, the row remains `unverified`. `0`, an empty cell, or a
planned budget must not be substituted for missing evidence.
