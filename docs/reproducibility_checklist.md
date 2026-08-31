# Reproducibility and publication checklist

Status: engineering checklist; unchecked items are not silently treated as passed.

## Before a run

- [ ] Protocol version and experiment registry are frozen and recorded.
- [ ] Train, validation, calibration and final-test inputs have disjoint sample IDs and template groups.
- [ ] Source revisions, licenses, input hashes and action provenance are recorded.
- [ ] The config is versioned; seed, input mode, label schema and threshold source are explicit.
- [ ] The output directory does not exist; failed runs will not be retried into a new hidden directory.
- [ ] The executor and authorization match the project boundary. Codex does not train, fit real
      calibration parameters or access formal final-test results.

## During and after model/calibration runs

- [ ] Start/end time, wall time, hardware, Python, PyTorch, Transformers, CUDA and actual cost are recorded.
- [ ] Checkpoint reload and metadata validation pass; checkpoint and config hashes are written.
- [ ] Calibration uses only the disjoint calibration split and records logits/input sidecar hashes.
- [ ] Threshold is selected only from calibration and is copied unchanged into evaluation reports.
- [ ] Raw predictions retain split, sample ID, template group, model revision and fixed threshold source.
- [ ] Missing runs, crashes, OOMs, ambiguous labels and negative results remain in the ledger.

## Statistical report

- [ ] Every preregistered seed is shown; mean/standard deviation do not replace per-seed results.
- [ ] Primary endpoints, bootstrap clustering, confidence intervals, effect sizes and Wilson intervals
      match `docs/research_protocol.md`.
- [ ] Any secondary p-values use Holm correction and are labeled exploratory.
- [ ] Error analysis stores IDs and non-content metadata, not raw private/untrusted text.
- [ ] The claim appears in `docs/claim_evidence_matrix.md` with all required artifact hashes.

## Deployment report

- [ ] FP32 and INT8 use the same frozen inputs, calibration and threshold.
- [ ] Export metadata binds source revision, model/tokenizer/artifact hashes and label mapping.
- [ ] Cold initialization, first request, warmed P50/P95, throughput, model size and peak RSS are recorded.
- [ ] API `/health`, `/v1/evaluate`, missing-model and malformed-artifact behavior are tested with mocks.
- [ ] No real send, upload, delete, payment, permission change or external tool side effect is used.

## Public release gate

- [ ] `python scripts/audit_public_release.py` passes on tracked files.
- [ ] `python -m ruff check .` passes.
- [ ] `python -m pytest -q` passes without unreviewed failures.
- [ ] `python -m compileall -q src baselines benchmarks scripts deployment` passes.
- [ ] `python -m build --wheel` passes.
- [ ] No raw/interim/processed data, checkpoint, ONNX/weight file, credential, personal data or
      generated result cache is tracked.
- [ ] Third-party license/attribution boundaries are preserved.
- [ ] Model card, data card, threat model, AI disclosure, limitations and negative findings agree.
- [ ] Project owner approves the exact public content before merge or release.
