# C2b Base 主实验运行准备手册

状态：工程准备已完成；Codex 不租用 GPU、不启动 Base 训练，也不拟合任何学习参数。
正式训练仍必须由项目所有者明确授权并亲自执行。默认人类审核路线保持不变；新增的
`2.2.0-ai-assisted-engineering.1` 只允许 AI-reviewed engineering training，不产生
`human_verified` 或 formal/paper-grade 证据。

## 1. 已冻结的运行边界

- Backbone：`microsoft/deberta-v3-base`，revision
  `8ccc9b6f36199bec6961081d44eb72fb3f7353f3`；
- 预注册 seeds：`42`、`52`、`62`；每个变体和 seed 必须使用独立配置与输出目录；
- C2b 计划使用单张 24GB GPU，规划上限 60 GPU 小时；实际费用必须由项目所有者记录；
- A/B/C 只改变输入模式，risk-only 与 action + Task Shield multitask 分开配置；
- train/validation 只用于训练和模型选择；calibration/test 仍不可提前访问或调参。

配置文件：

| 变体 | 配置 | 输入 | Alignment loss |
|---|---|---|---:|
| A risk-only | `configs/deberta_base_text_risk.yaml` | text | 0.0 |
| B risk-only | `configs/deberta_base_context_risk.yaml` | context | 0.0 |
| C risk-only | `configs/deberta_base_action_risk.yaml` | action | 0.0 |
| C multitask | `configs/deberta_base_action_multitask.yaml` | action | 0.5 |

## 2. 只读 preflight

`run_c2b_base.ps1` 目前只接受 candidate 8，并会先解析唯一的 `intentfence` Conda Python，检查已冻结的 Base 配置契约
（revision、超参数、输入模式、loss 目标和预注册 seed），再绑定 candidate manifest 的
train/validation 路径与字节哈希，最后检查依赖、CUDA 信息并调用 `intentfence.train --dry-run`
检查 split、benign/attack 覆盖、action 和 optimizer-step 计划。`-PreflightOnly` 不加载
tokenizer、模型或 checkpoint，也不会接受脱离 candidate manifest 的替代数据：

```powershell
Set-Location E:\IntentFence
.\scripts\run_c2b_base.ps1 `
  -ConfigPath configs\deberta_base_action_multitask.yaml `
  -TrainPath data\interim\route_b_v2_candidate_8\train.jsonl `
  -ValidationPath data\interim\route_b_v2_candidate_8\validation.jsonl `
  -OutputDirectory checkpoints\base-action-multitask-seed42 `
  -PreflightOnly
```

在当前 CPU 主机上只允许运行上述预检；不要为了验证脚本而传入 `-RequireCuda` 或启动训练。

## 3. 正式训练授权文件

非预检运行必须由项目所有者在独立人类审核与裁决完成后自行创建授权文件。Codex 不填写该
文件，也不把 AI 审核结果转换为授权。文件至少需要以下字段：

```json
{
  "schema_version": 1,
  "candidate_id": "route_b_v2_candidate_8",
  "human_verified": true,
  "formal_training_authorized": true,
  "approved_by_project_owner": "<owner id>",
  "approved_at": "<timezone-aware ISO-8601 timestamp>",
  "protocol_version": "2.0.0",
  "candidate_manifest_sha256": "<file SHA-256 of candidate manifest>",
  "readiness_report_sha256": "<file SHA-256 of readiness.json>",
  "protocol_lock_sha256": "<file SHA-256 of route_b_protocol_lock.json>"
}
```

这里的 `protocol_version` 必须是已冻结的 Route B `2.0.0`；旧的通用 `1.0.0` 协议锁不能作为
candidate 8 Base 训练授权。脚本会在任何非预检训练启动前，校验授权文件、candidate manifest、
readiness 报告、协议锁、完整性报告和正式人类审核证据的路径与哈希绑定，并核对实际传入的
train/validation 文件路径与字节哈希确实对应 candidate manifest；缺少冻结证据、训练输入漂移
或使用旧授权文件都会被拒绝。实际 Base 训练 CLI 也会再次要求同一组授权参数并重验授权，
不会只依赖外层 PowerShell 包装器。上面三个哈希是文件字节 SHA-256，不是 manifest 内嵌的
sealed canonical 哈希。

完整运行命令由项目所有者亲自执行，并且必须显式提供 CUDA、实际人民币成本和独立输出目录：

```powershell
.\scripts\run_c2b_base.ps1 `
  -ConfigPath configs\deberta_base_action_multitask.yaml `
  -TrainPath data\interim\route_b_v2_candidate_8\train.jsonl `
  -ValidationPath data\interim\route_b_v2_candidate_8\validation.jsonl `
  -OutputDirectory checkpoints\base-action-multitask-seed42 `
  -AuthorizationFile data\interim\route_b_v2_candidate_8\training_authorization.json `
  -CostCny 0 `
  -RequireCuda
```

脚本拒绝覆盖已有输出，失败时不自动重试；训练后必须通过 checkpoint reload，并生成绑定
commit、配置/数据哈希、seed、硬件、时长、实际成本和 checkpoint 文件哈希的
`run_manifest.json`。完成一个变体后先停下，不能直接运行下一个变体。

## 4. 多 seed 汇总与统计

每次运行完成后，项目所有者应从各自的 `run_manifest.json` 与评估结果建立一个只包含实际
运行的 `runs.json`，再使用：

```powershell
python scripts/summarize_seed_runs.py `
  --input artifacts\c2b\runs.json `
  --output reports\c2b\seed_summary.json
```

该命令只汇总显式提供的 per-seed 标量，不补造缺失 seed，也不产生 bootstrap 结果。配对的
per-sample 安全指标使用 `intentfence.statistics.paired_bootstrap_difference`，固定阈值必须
来自 calibration，不能从 Test A/B/C 重新选择。该函数实现预注册的
`paired_cluster_percentile_with_seed_outer_stratum`，默认 10,000 次重采样和 95% percentile
区间；效应量使用配对差值和 Cohen's dz。次要 p 值若报告，须在同一结果表内使用 Holm 校正。

NotInject 仍报告精确误报数与 Wilson 区间，不把 339 条压力样本包装成生产精度证明。

## 5. 当前边界

candidate 8 的人工 v2 审核仍未完成，当前授权文件不存在，因此本手册只证明 C2b 工程入口
可检查、可审计、可拒绝越权运行；不证明模型有效，也不授权训练、校准或最终测试。

## 6. AI-reviewed engineering training route

项目所有者已明确选择新增路线 `B-ai-assisted-engineering`。这条路线使用两个不同的
provider/model/revision，以温度 `0` 独立完成同一标签中性包的 400 条 Risk 与 400 条
Alignment/action 审核；AI 输出必须保留原始文件和哈希，且始终标记为
`ai_reviewed_engineering_only`。它可以替代本手册中“工程训练前必须完成两名人类审核”的
前置条件，但不能替代人类审核证据、正式研究训练、校准或最终测试。

协议、锁和就绪报告路径：

```powershell
$Candidate = "data/interim/route_b_v2_candidate_8"
$AiPair = "data/interim/route_b_v2_candidate_8_human_audit_v2_ai_pair"
$AiAudit = "data/interim/route_b_v2_candidate_8_ai_pair_audit"

python scripts/freeze_route_b_ai_training_protocol.py `
  --confirm-project-owner-approval

上面的 freeze 命令只用于首次生成锁；本工作树已有
configs/route_b_ai_training_protocol_lock.json 时不要重复执行（脚本会拒绝覆盖），只需
运行 scripts/validate_route_b_ai_training_framework.py 验证现有锁，然后继续生成 readiness。

python scripts/build_route_b_ai_training_readiness.py `
  --candidate-manifest "$Candidate/manifest.json" `
  --integrity-report "$Candidate/integrity_v2_data_protocol.json" `
  --ai-review-analysis "$AiPair/ai_review_analysis.json" `
  --ai-review-manifest "$AiPair/ai_review_manifest.json" `
  --audit-manifest "$AiAudit/audit_manifest.json" `
  --public-report reports/data_quality/route_b_candidate_8_ai_engineering_card.md `
  --output "$Candidate/ai_engineering_readiness.json"
```

当质量门失败时，readiness 仍会如实保留失败结果；只有在结构证据通过后，项目所有者才可
在独立授权文件中填写风险接受理由。授权文件至少包含：

```json
{
  "schema_version": 1,
  "candidate_id": "route_b_v2_candidate_8",
  "protocol_version": "2.2.0-ai-assisted-engineering.1",
  "training_authorization_mode": "ai_reviewed_engineering",
  "human_verified": false,
  "formal_training_authorized": false,
  "engineering_training_authorized": true,
  "training_executor": "project_owner_only",
  "ai_evidence_class": "ai_reviewed_engineering_only",
  "ai_quality_gate_failure_accepted": true,
  "ai_quality_gate_failure_reason": "<owner's reasoned engineering-only risk acceptance>",
  "approved_by_project_owner": "<owner id>",
  "approved_at": "<timezone-aware ISO-8601 timestamp>",
  "candidate_manifest_sha256": "<file SHA-256>",
  "readiness_report_sha256": "<file SHA-256>",
  "protocol_lock_sha256": "<file SHA-256>",
  "integrity_policy_sha256": "<file SHA-256>",
  "ai_review_policy_sha256": "<file SHA-256>",
  "ai_review_analysis_sha256": "<file SHA-256>",
  "ai_review_manifest_sha256": "<file SHA-256>"
}
```

将 `-AuthorizationFile $Candidate\ai_training_authorization.json`、
`-PolicyPath configs\route_b_ai_training_protocol.yaml`、
`-ProtocolLockPath configs\route_b_ai_training_protocol_lock.json`、
`-ReadinessReportPath $Candidate\ai_engineering_readiness.json`、
`-AuditAnalysisPath $AiPair\ai_review_analysis.json`、
`-AuditManifestPath $AiAudit\audit_manifest.json`、
`-PublicReportPath reports\data_quality\route_b_candidate_8_ai_engineering_card.md`、
`-AiReviewManifestPath $AiPair\ai_review_manifest.json`、
`-IntegrityPolicyPath configs\route_b_data_protocol.yaml`、
`-AiReviewPolicyPath configs\route_b_ai_review_protocol.yaml` 传给 `run_c2b_base.ps1`，即可让
入口校验 2.2 AI 授权。若使用当前 candidate 8 包，还必须将当前失败的 Risk/Alignment
质量门写入上述接受理由；不能删改原始 CSV 或降低阈值。训练仍须显式 `-RequireCuda`、
记录实际成本，并在完成一个变体后停止。

这条路线不会打开 calibration、Test A/B/C/D、最终测试或发表结论；这些阶段仍需单独的
项目所有者授权和冻结证据。
