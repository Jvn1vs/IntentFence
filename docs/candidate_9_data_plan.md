# Candidate 9 多来源训练数据方案

状态：2026-09-08 已构造 candidate_9_v2，3620 条，完整性验证通过；仍未训练就绪。实际执行规则由 configs/candidate_9.yaml 记录，后文原 80/10/10 方案保留为历史草案，已由独立 calibration 的 70/10/10/10 组划分替代。本文不授权直接训练。

## 最新构造结果

见 `reports/data/candidate_9_build_20260908.md`。train/validation/calibration/internal Test A 为 2550/357/351/362 条。由于锁定集合排除，Email 仅保留 1 个公开背景，当前候选仍以 Table 为主，不能称为已经解决分布单一问题。16 条 authored 困难负样本仅是初始素材。完整性通过不等于标签审核、五类 Risk、独立 Alignment 或动作数据门通过。

## 2026-09-08 执行发现与适用修正

- 本地 BIPIA 99 个、InjecAgent 24 个登记文件均通过源 manifest 的大小和 SHA-256 核验，Git revision 与冻结注册表一致，无需重复下载。
- BIPIA 官方 train 原始行数：Email 50（45 个规范化不同背景）、Table 900（617 个背景）、Code 50（50 个背景）。这些是背景/问题行数，不是独立攻击数量，也不是最终训练规模。
- Email 50 与 Table 900 条已使用现有严格适配器转换到 `data/interim/candidate_9_source_audit_20260908/`，各自 skipped=0，split=null、human_verified=false、action_provenance=missing。此为待审核素材，不是可直接训练的冻结数据。
- InjecAgent 的 dh 30/30、ds 32/32 条攻击指令，以及 17/17 条用户指令，与四份官方 base/enhanced test 文件存在规范化精确重叠。按原方案“不得复用官方 test 攻击者文本”的规则，原子重组训练路线无剩余素材；本候选排除该训练来源，保留 Test B。这是隔离检查结果，不是模型评测。
- CodeQA 的 context 是列表，任务输入为 code/error，不能直接套用要求 question 的 clean 适配器。后续适配须保留 context_url/context_author_url，继续核对 Stack Exchange 数据条款，不能仅凭仓库 MIT 声明覆盖上游素材。
- 下面的 InjecAgent 重组设计保留为历史条件方案，本次检查已触发其“整部分只作评测”的退出条件。
- 当前 80/10/10 草案未单列 calibration；正式构造前须版本化修订并明确独立 calibration 的分配。不能使用 candidate 8 的校准集填补这一空缺后声称与新公开来源隔离。
- 必须先隔离背景组和攻击家族再配对；完整笛卡尔积后要求两者都不跨 split，可能形成连通大组，不能靠随机拆行解决。大量组合也不应被报告为同等数量的独立语义场景。

核验汇总与可复现命令见 `reports/data/candidate_9_source_audit_20260908.md`。

## 目标

保留 candidate 8 的第一轮工程结果作为历史基线，降低单一 project-owned mock 模板造成的分布依赖。candidate 9 引入 BIPIA 的官方训练 split，并从 InjecAgent 的原子 user/attacker cases 构造不与官方 test cases 重合的 project-derived 训练数据；官方 InjecAgent 组合 test cases 继续作为 Test B 外部评测。

## Split 设计

### BIPIA

- 输入：官方 `benchmark/{task}/train` context 文件和对应 train attack 文件；每个 task 单独保留 source provenance。
- 先按 task、attack 类型、context/template family 分组，再做固定 seed 的 80% train / 10% validation / 10% internal Test A 划分。
- 同一 context、攻击模板家族或近重复组不得跨三个 split；内部 Test A 只用于 candidate 9 的受控外部留出，不用于训练或调参。
- BIPIA 官方 `test` 文件及其生成结果不进入 candidate 9 训练、validation 或 calibration，作为独立外部评测输入。
- WebQA 与 Summarization 只能在上游许可证和下载条款被记录并允许后纳入；否则排除并在 manifest 写明理由。

### InjecAgent

- 官方仓库的 `test_cases_dh_{setting}.json`、`test_cases_ds_{setting}.json`（base/enhanced）全部保持 Test B 外部评测，不拆分、不训练。
- 仅从 `user_cases.jsonl`、`attacker_cases_dh.jsonl` 和 `attacker_cases_ds.jsonl` 的原子素材重新组合，构造 project-derived training pool；不复用官方 test 的完整组合、攻击者文本、用户工具组合或可检测近重复。
- 对重新组合后的样本按 user case、attacker family、tool pair 分组，固定 seed 做 80% train / 10% validation / 10% internal holdout；组合规则、生成器版本和排除列表写入 manifest。
- 该部分在报告中标记为 `InjecAgent_project_derived`，不得称为 InjecAgent 官方 train split。若无法证明组合与官方 test 隔离，则整部分只作评测，不作训练。

## 合并规则

- candidate 9 的 train/validation 只能包含 BIPIA 官方 train-derived 数据、InjecAgent project-derived 数据和新建的非模板化 project-owned hard negatives。
- calibration、Test A、Test B、Test C、Test D 仍保持角色隔离；Test B 是官方 InjecAgent 组合评测，不能因引入 project-derived 训练样本而解锁。
- Risk 与 Alignment 标签必须分别记录 source label、IntentFence label mapping、mapping rationale 和不确定项；不能把 InjecAgent 的 attack intent 自动当成五类 Risk 或四类 Alignment。
- 统一执行精确去重、近重复检测、模板族隔离和 source-level holdout；任何泄漏都 fail-closed。

## 需要生成的证据

1. 每个上游仓库的 commit/tag、LICENSE、数据条款、下载时间和原始文件 SHA-256。
2. BIPIA 每个 task 的输入/输出 builder report、转换报告和 split manifest。
3. InjecAgent 原子重组生成器的版本哈希、随机种子、组合排除规则和与官方 test 的重叠检查。
4. candidate 9 manifest：每个角色的路径、来源、行数、标签分布、模板组、近重复统计和 SHA-256。
5. 数据卡、标签映射说明、许可证清单和训练前质量报告。

## 阶段边界

- 本阶段先完成来源复核、协议修订、转换/去重/划分和质量报告；不启动模型训练。
- candidate 9 协议必须明确替代 candidate 8 的适用范围，但不得修改 candidate 8 历史 manifest、报告或 checkpoint 记录。
- 公开 benchmark 的官方 test 仍是评测证据；任何训练后指标必须标记为工程或研究证据等级，不能把内部 holdout 当作最终测试。
