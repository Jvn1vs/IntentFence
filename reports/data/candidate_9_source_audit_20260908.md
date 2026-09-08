# Candidate 9 来源核验与初步转换

日期：2026-09-08。执行者：Codex。阶段结果：来源检查与 Email/Table clean 转换完成；完整训练集未就绪。

## 实际结果

| 来源 | 官方 train/原子行数 | 本次结果 |
|---|---:|---|
| BIPIA Email | 50 | 45 个不同规范化背景；严格转换 50 条，skipped=0 |
| BIPIA Table | 900 | 617 个不同规范化背景；严格转换 900 条，skipped=0 |
| BIPIA Code | 50 | 50 个不同规范化背景；字段与邮件适配器不兼容，未转换 |
| InjecAgent dh | 30 | 30 条攻击指令均与官方测试重叠，训练排除 |
| InjecAgent ds | 32 | 32 条攻击指令均与官方测试重叠，训练排除 |
| InjecAgent user | 17 | 17 条用户指令均与官方测试重叠，训练排除 |

指令重叠采用 NFKC、casefold、空白归一化后的精确相等；这足以否定当前原子重组方案的独立性，但不是通用语义近重复证明。背景计数是各任务内 context 的规范化去重，并未完成跨任务或跨来源近重复检查。不能将 950 条已转换素材称为 950 条新增、独立或已审核训练样本；Email 原始来源先前已用于 C1。

核验 BIPIA 的 99 个、InjecAgent 的 24 个登记文件，大小和 SHA-256 全部一致。revision 分别为 `a004b69ec0dd446e0afd461d98cb5e96e120a5d0` 与 `f19c9f2c79a41046eb13c03c51a24c567a8ffa07`。源 manifest SHA-256 为 `fe5bb40f5c904f8042aaf546fb9f4e526e09e941ea965cbb96306766823b6cdf`。

## 本地产物

目录：`data/interim/candidate_9_source_audit_20260908/`（忽略，不公开原文）。

- `report.json`：来源核验和重叠计数。
- `email_clean.jsonl` 与转换报告；输出 SHA-256 `2f84705915b4be04fa9eaaffaf8b7b841f140ba9d77d0259b47b654db30f2d3e`。
- `table_clean.jsonl` 与转换报告；输出 SHA-256 `350b429721a983614046478ec86b7f62992941d6756afea851d482fff93d271b`。

转换保留现有 legacy schema：risk=benign、二元 alignment_label=0；Task Shield 四类 task_alignment_label 未标注。所有行 split=null、human_verified=false、缺少动作。这些标签不构成独立 Alignment 人审，不能直接供 C multitask 训练。

## 复现

使用 Conda `intentfence`，以下输出均不得已存在：

```powershell
conda activate intentfence
python scripts/audit_candidate_9_sources.py --output data/interim/candidate_9_source_audit_20260908/report.json
python scripts/prepare_bipia.py --input data/raw/bipia/benchmark/email/train.jsonl --output data/interim/candidate_9_source_audit_20260908/email_clean.jsonl --kind clean --task-name email
python scripts/prepare_bipia.py --input data/raw/bipia/benchmark/table/train.jsonl --output data/interim/candidate_9_source_audit_20260908/table_clean.jsonl --kind clean --task-name table
```

另行复现应换用一个新的输出目录。源码测试覆盖“换用户仍复用攻击原文”的重叠检测，以及空隔离字段拒绝。

## 后续入口

验证：Ruff、compileall、wheel 构建通过；新增 2 项隔离测试通过；全量测试 262 passed、1 failed。失败为 `test_c1_framework_contract_is_valid`：已有 `configs/execution_policy.yaml` 缺少 validator 要求的 `run_small_or_base_model_training_or_tiny_overfit` 禁止项。该配置在 HEAD 已是此状态，本轮未修改执行授权配置；因此不能声称全套测试通过。当前工作按 AGENTS.md 的项目所有者独占训练边界执行。

先修订 candidate 9 构造协议：独立 calibration；背景与攻击家族双重隔离的配对规则；CodeQA 适配与上游条款；多样化攻击和困难负样本；五类 Risk/四类 Alignment 的证据缺口。然后生成去重后的正式 splits 和 manifest。BIPIA 官方完整组合量不能替代独立背景量；不能把所有攻击无审查地映射成同一种风险并宣称五分类覆盖。

本轮没有训练、校准、最终测试模型运行或额外付费。candidate 8 产物保持原状。InjecAgent 改作仅评测是预先记录的失败退出条件，未改变正式测试内容。
