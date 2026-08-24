# C1 label quality report

Status: generated from project-owner data artifacts; review the machine-readable statistics alongside this report.

## Human audit

- Completed rows: 200
- Decisions: `{"correct": 200}`
- Decision rates: `{"correct": 1.0}`
- Reviewer counts: `{"project_owner": 200}`
- Applied outcomes: `{"confirmed": 200, "unaudited_retained": 11100}`
- Inter-reviewer agreement: not measured unless a separately versioned second-review artifact is supplied.

## Risk × Alignment contingency

Scope: train split only; final-test labels are not used for this dependency decision.

| Risk label | Alignment 0 | Alignment 1 |
|---|---:|---:|
| benign | 39 | 0 |
| instruction_hijacking | 0 | 1176 |
| data_exfiltration | 0 | 0 |
| privilege_escalation | 0 | 0 |
| tool_manipulation | 0 | 0 |

- Mutual information: 0.20481026 bits (0.14196365 nats).
- Alignment entropy: 0.20481026 bits.
- Alignment is deterministic from risk: `true`.

The full conditional-probability tables are stored in `dataset_statistics.json`. A deterministic mapping means the auxiliary label contains no independent label information; only a preregistered model ablation can test optimization effects.
