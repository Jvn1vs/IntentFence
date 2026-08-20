# Reliability and failure policy

Policy version is tracked independently from model and calibration versions.

| Tool type | Examples | Detector failure | Low-score minimum |
|---|---|---|---|
| `read` | public search/read | restricted fail-open | allow |
| `local_write` | local draft/temp file | require confirmation | confirm when uncalibrated |
| `external_communication` | email/upload/message | fail-closed | confirm |
| `sensitive` | delete/pay/permissions | fail-closed | confirm |

`restricted fail-open` permits only the original read; it cannot be automatically upgraded into a write or communication action. A timeout, missing model, malformed result or unavailable calibration is never converted to a benign score.

The model emits risk and alignment scores. The policy takes the maximum, applies the configured tool weight, and compares that non-probabilistic policy risk to frozen decision thresholds. High-risk tool invariants then raise the minimum decision. Every response contains deterministic reason codes and model/calibration/policy version metadata.

Long-document maximum/Top-k aggregation breaks sample-level calibration. Such output is explicitly marked document-level and must use conservative thresholds or confirmation until a fixed chunking/aggregation method has its own disjoint document calibration set.
