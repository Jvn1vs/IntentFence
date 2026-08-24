# IntentFence C1 data card

Status: project-owner generated derivative dataset. The BIPIA training pool has a human-label audit gate; Test B/C have schema, provenance, and integrity gates but not an equivalent human-label audit.

## Version and intended use

- Split manifest SHA-256: `bdd9fe80de528083591652bc743d878777adb55bb082bf4d5df6fc5f7d1f0063`
- Intended use: offline research on indirect prompt-injection detection under the frozen IntentFence protocol.
- Not intended for: production safety guarantees, authorization decisions, or claims about observed Agent actions.

## Sources

| Source | Revision | License finding |
|---|---|---|
| bipia | `a004b69ec0dd446e0afd461d98cb5e96e120a5d0` | MIT code; task datasets retain separate source licenses |
| injecagent | `f19c9f2c79a41046eb13c03c51a24c567a8ffa07` | MIT |
| notinject | `847ae76cf8fea5ed325429e569ae8cfef022d2e0` | MIT |

## Split composition

| Split | Rows | Risk counts | Action provenance |
|---|---:|---|---|
| train | 1215 | `{"benign": 39, "instruction_hijacking": 1176}` | `{"missing": 1215}` |
| validation | 493 | `{"instruction_hijacking": 493}` | `{"missing": 493}` |
| calibration | 493 | `{"instruction_hijacking": 493}` | `{"missing": 493}` |
| test_a | 486 | `{"instruction_hijacking": 486}` | `{"missing": 486}` |
| test_b | 1054 | `{"data_exfiltration": 544, "tool_manipulation": 510}` | `{"benchmark_target": 1054}` |
| test_c | 339 | `{"benign": 339}` | `{"protocol_wrapper": 339}` |

## Conversion provenance

| Adapter profile | Converted | Skipped | Output SHA-256 |
|---|---:|---:|---|
| bipia_generated_v1 | 11250 | 0 | `d485aeada57cb05fa97fe3436b5efbbfbbe53caec3b861840de138a5e52e036b` |
| bipia_clean_v1 | 50 | 0 | `449a135cddc8d0c882af2b86e0051b034b8d483c84059679134900985f953e4f` |
| injecagent_direct_harm_v1 | 510 | 0 | `10b8decb5a34694abfd8dd07dfe72c563a94584742cf0892109a1f633e01851c` |
| injecagent_data_stealing_v1 | 544 | 0 | `e52aa46b4aed9fa722eb9caadbfe85c1b715638297cac3bf96b47ddd5bb49224` |
| notinject_v1 | 113 | 0 | `ae0bfa1a1c945cf5efca365e3ab35a65567028d4b87c8cfe4fa33527b46cde03` |
| notinject_v1 | 113 | 0 | `ae2b993b8c20e7c3245fd7bd26eee64514ecea040f949e1569c8a80ce129f763` |
| notinject_v1 | 113 | 0 | `d349d441adf039f3420dacdb492ed565834bd43ee84c9ea1d201e7bea1304f93` |

## Training-readiness findings

- Assessment scope: class presence and action-evidence gates only; this is not formal training authorization.
- Binary benign/attack class coverage present in train: `true`
- Five-class coverage present in train: `false`
- Missing train risk labels: `["data_exfiltration", "privilege_escalation", "tool_manipulation"]`
- Minimum per-class support assessed: `false`.
- Alignment target has independent label information: `false`
- Model C action data ready: `false`
- Formal training authorized: `false` (project-owner protocol/action-route decision pending).

## Action-evidence boundaries

- BIPIA rows do not provide a real proposed action until a separately approved and audited action-construction stage exists.
- InjecAgent `benchmark_target` is a benchmark target, not an observed Agent proposal or tool call.
- NotInject `protocol_wrapper` is a fixed over-defense probe, not source-provided Agent behavior.

## Known limitations

- External detector training overlap is not known at membership level.
- NotInject is a small trigger-enriched stress set, not representative benign traffic.
- A missing risk class in train cannot support a five-class learned claim for that class.
- Human-verified flags apply only to reviewed rows; unreviewed retained rows remain unverified.
- Test B/C labels pass schema and integrity checks but are not covered by the BIPIA human-audit sample.
- Final-test label counts are descriptive provenance already sealed in the manifest and must not be used to tune models, thresholds, or configurations.
