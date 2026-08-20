# IntentFence repository guidance

## Project workflow

- Treat `docs/task_progress_plan.md` as the single source of truth for stages,
  status, tests, and exit criteria.
- Work on one stage at a time. At the end of every stage, stop and report the
  changed files, verification results, remaining risks, and proposed next step.
- Do not start the next stage until the user explicitly confirms it.
- Do not rent GPU capacity, call paid APIs, publish a release, or download large
  model/data artifacts without explicit user approval for that stage.

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
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q src baselines benchmarks scripts deployment
.\.venv\Scripts\python.exe -m build --wheel
```
