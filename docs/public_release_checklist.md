# Public release checklist

Status: `NOT READY` for merge/release. This checklist prepares the repository; it does not publish
anything and does not authorize a final-test run.

## Automated gate

Run from the repository root:

```powershell
conda activate intentfence
python scripts/audit_public_release.py
python scripts/audit_public_release.py --include-untracked
python -m ruff check .
python -m pytest -q
python -m compileall -q src baselines benchmarks scripts deployment
python -m build --wheel
```

The audit examines tracked files and, in the second invocation, non-ignored untracked files. It
rejects raw/interim/processed data, checkpoints, model/ONNX weights, generated result caches,
private/output directories, unlisted JSON, common tabular/serialized/binary formats, `.env` files
and high-confidence secret patterns. Only the recorded protocol JSON files and the synthetic smoke
fixture are allowed by explicit rule; `.gitkeep`, `.env.example` and public Markdown cards are
also allowed where the path rules permit them.

## Manual gate

- [ ] Review the exact Git diff and tracked-file list.
- [ ] Recheck every source license and attribution against the pinned source record.
- [ ] Confirm no private data, credentials, raw third-party data, checkpoint or ignored result cache
      is included in the intended release artifact.
- [ ] Confirm model card, data card, threat model, reliability policy and AI disclosure agree.
- [ ] Confirm all quantitative claims map to `docs/claim_evidence_matrix.md`.
- [ ] Confirm negative findings and missing experiments are visible.
- [ ] Project owner approves public content and any merge/release separately.

## Current blockers

There is no trained checkpoint, real calibration report, formal Test A/B/C output or real FP32/INT8
latency report in the public source tree. The current C3b smoke evidence is engineering-only. The
Route B independent human audit, training authorization and final-test lock remain unchanged.
