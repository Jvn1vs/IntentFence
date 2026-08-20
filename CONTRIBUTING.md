# Contributing

Open an issue before large changes. Keep training data and checkpoints out of Git, preserve source/license metadata, and never tune on a final test split.

Every code change should pass:

```text
python -m ruff check .
python -m pytest
```

Result contributions must include the exact commit, data manifest hash, model/config version, random seed, hardware, calibration artifact and raw prediction file. Negative results are welcome; unverifiable benchmark claims are not.
