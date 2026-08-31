# C2b Base 主实验运行准备手册

状态：工程准备已完成；Codex 不租用 GPU、不启动 Base 训练，也不拟合任何学习参数。
正式训练只有在项目所有者完成独立人类审核、明确授权并亲自执行后才能发生。

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
