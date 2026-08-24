# IntentFence 训练入口决策记录

## Material Passport

- Origin Skill: academic-research-suite / experiment-agent
- Origin Mode: reproducibility planning
- Prepared: 2026-08-23
- Status: `PENDING_PROJECT_OWNER_DECISION`
- Authority: 本文件不是协议修订；`docs/research_protocol.md` 与 `configs/experiment_registry.yaml` 仍保持冻结状态

## 为什么训练入口尚未开放

当前数据构造和 schema 已经暴露三项独立阻塞：

1. BIPIA 训练池天然只有 `benign` 与 `instruction_hijacking`。除非人工审计产生有充分证据的修订，否则 `data_exfiltration`、`privilege_escalation` 和 `tool_manipulation` 没有训练正例，不能支持五分类 risk head 的论文结论。
2. schema 强制 `benign → alignment_label=0`、所有非 benign risk → `alignment_label=1`，所以 Alignment 是 Risk 的确定性函数。它不是独立标注信息；H4 至多能解释为“重复二值辅助损失的优化效应”。
3. BIPIA 没有真实 `proposed_action`。在动作构造、provenance 和独立真实性审计获批前，Model C 不能使用真实项目数据训练或形成结论。

这些判断会由项目所有者运行 `scripts/build_dataset_reports.py` 后的 `dataset_statistics.json` 再次以真实计数验证。在该报告产生前，不修改冻结假设，也不启动正式训练。

## 选项 A：二元 risk-only 主目标（推荐的最小路线）

- Primary 模型预测 `benign` 与 `attack`，与 H1/H2/H3 的 TPR/FPR 主端点一致。
- 五类 `risk_label` 继续保留，用于数据来源记录、分层错误分析和有证据的逐类描述；不声称五类均被监督学习。
- A/B/C 的 primary 训练使用 risk-only。
- Alignment 可作为明确标注为“确定性重复目标”的探索性辅助损失消融；H4 不再解释为独立标签信息增益。
- Model C 仍必须等待获批的动作构造与独立真实性审计，不能因改成二元目标而绕过 action gate。

该选择属于实质性协议修订。必须在正式 split/训练/性能测试前创建新协议版本、更新 protocol lock，并记录原 H4 解释的变更原因。当前尚未运行正式 Test A/B/C 性能，因此现在是成本最低的修订窗口。

## 选项 B：保留五分类与独立多任务目标

需要在训练前全部完成：

- 增加经许可、只进入训练来源的 `data_exfiltration`、`privilege_escalation`、`tool_manipulation` 样本；不得从 Test B/C 挪用；
- 为 train/validation/calibration/test_a 构造或捕获真实语义的 proposed action；
- 对动作 realism/provenance 做独立人工审计；
- 收集不由 risk 标签规则推导的独立 Alignment 标注，并报告一致性；
- 重新生成 manifest、标签报告和训练就绪报告。

这条路线工作量更大，但只有它能维持“五分类 + 独立 Alignment 监督”的原始解释。

## 选项 C：仅做 A/B 工程冒烟

在 C1 context gate 通过后，项目所有者可以只用 train/validation 做 A/B 工程冒烟，用于验证 tokenizer、forward/backward 和 checkpoint reload。限制如下：

- 不读取 calibration 或 Test A/B/C 性能；
- 不构成 H1/H2/H4 研究结论；
- 后续共同数据/协议冻结后必须重跑；
- 真实 Model C 仍禁止开始。

## 项目所有者需要确认的决定

在真实 `dataset_statistics.json` 生成并复核后，项目所有者应在本文件记录：

- 选择：`A` / `B` / `C-only-smoke`；
- 决定日期与决定人；
- 是否批准新协议版本；
- 是否批准动作构造与独立审计阶段；
- 若涉及外部模型或新增数据，许可、下载范围与预算边界。

在上述字段未确认前，状态保持 `PENDING_PROJECT_OWNER_DECISION`，正式模型训练入口关闭。
