# IntentFence repository guidance

## Project workflow

- Treat `docs/task_progress_plan.md` as the single source of truth for stages,
  status, tests, and exit criteria.
- Use Conda for every project environment. The default CPU/data environment is
  named `intentfence`; do not create or document a project `.venv`. Use the
  official Anaconda and PyPI endpoints, not third-party package mirrors.
- Work on one stage at a time. At the end of every stage, stop and report the
  changed files, verification results, remaining risks, and proposed next step.
- Do not start the next stage until the user explicitly confirms it.
- Do not rent GPU capacity, call paid APIs, publish a release, or download large
  model/data artifacts without explicit user approval for that stage.
- The user is the sole executor of real data and training runs. Codex may build
  and test the framework, generate configs/commands, and analyze user-provided
  logs, but must not download, convert, merge, deduplicate, split, or audit real
  project data; fit a learned baseline; update real model weights; run tiny-
  overfit training; rent training hardware; or incur training/API charges.
- Framework verification may use static checks, fixtures, mocks, and tests that
  do not fit learned parameters on real project data.
- `configs/execution_policy.yaml` is the machine-readable execution boundary.

## Research integrity

- Never invent citations, dataset properties, experimental results, or metrics.
- Keep training, validation, calibration, and final test sets disjoint. Do not
  tune models, prompts, temperatures, policies, or thresholds on final tests.
- Record upstream revisions and licenses, file hashes, configurations, seeds,
  dependency versions, hardware, duration/cost, and raw predictions needed to
  reproduce every reported result.
- Distinguish implemented, smoke-tested, and experimentally verified claims.
- Use the Task Shield label set exactly: `aligned`, `unrelated`, `ambiguous`,
  and `malicious`.

## Data and security

- Never commit credentials, `.env`, personal data, raw third-party datasets,
  model checkpoints, generated result caches, or other ignored artifacts.
- Use mocked or sandboxed actions in tests; tests must not perform real external
  side effects.
- Preserve source-specific licenses and attribution. The repository's
  Apache-2.0 license does not override third-party dataset/model licenses.

## Code conventions

- Target Python 3.10+ and keep importable code under `src/intentfence`.
- Prefer typed, deterministic code; validate public inputs with the Pydantic
  schemas and expose experimental choices through versioned configuration.
- Add or update tests with behavior changes. Keep generated files out of source
  control unless they are explicitly approved reproducibility artifacts.

## Local verification

```powershell
conda activate intentfence
python -m ruff check .
python -m pytest -q
python -m compileall -q src baselines benchmarks scripts deployment
python -m build --wheel
```
