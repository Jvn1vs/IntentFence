# IntentFence 训练入口决策记录

## Material Passport

- Origin Skill: academic-research-suite / experiment-agent
- Origin Mode: reproducibility planning
- Prepared: 2026-08-23；真实证据复核：2026-08-24
- Status: `C1_EVIDENCE_VALIDATED_TRAINING_BLOCKED`
- Authority: 本文件不是协议修订；`docs/research_protocol.md` 与 `configs/experiment_registry.yaml` 仍保持冻结状态

## 为什么训练入口尚未开放

`reports/data_quality/dataset_statistics.json` 已生成并通过整条来源、转换、审核、去重、划分和完整性证据重放。当前数据构造和 schema 已经验证四项独立阻塞：

1. BIPIA 训练池天然只有 `benign` 与 `instruction_hijacking`。除非人工审计产生有充分证据的修订，否则 `data_exfiltration`、`privilege_escalation` 和 `tool_manipulation` 没有训练正例，不能支持五分类 risk head 的论文结论。
2. schema 强制 `benign → alignment_label=0`、所有非 benign risk → `alignment_label=1`，所以 Alignment 是 Risk 的确定性函数。它不是独立标注信息；H4 至多能解释为“重复二值辅助损失的优化效应”。
3. BIPIA 没有真实 `proposed_action`。在动作构造、provenance 和独立真实性审计获批前，Model C 不能使用真实项目数据训练或形成结论。
4. 去重后的 train 只有 39 条 benign/1,176 条 instruction_hijacking；validation 493、calibration 493、test_a 486 均只有 instruction_hijacking，没有 benign。当前版本不能进行有意义的二分类模型选择、FPR 估计或校准。

真实数据证据状态为 `validated`，总计 4,080 条；训练就绪报告明确给出 `formal_training_authorized=false`。统计 JSON SHA-256 为 `f9008ff67c7f307ae2544695091625a861f22d78950238802c08946cf4f4f81f`，公开聚合结论见 `reports/data_quality/data_card.md` 与 `reports/data_quality/label_quality_report.md`。不得把“报告已生成”误解为“数据已适合训练”。

## 选项 A：二元 risk-only 主目标（推荐的最小路线）

- Primary 模型预测 `benign` 与 `attack`，与 H1/H2/H3 的 TPR/FPR 主端点一致。
- 五类 `risk_label` 继续保留，用于数据来源记录、分层错误分析和有证据的逐类描述；不声称五类均被监督学习。
- A/B/C 的 primary 训练使用 risk-only。
- Alignment 可作为明确标注为“确定性重复目标”的探索性辅助损失消融；H4 不再解释为独立标签信息增益。
- Model C 仍必须等待获批的动作构造与独立真实性审计，不能因改成二元目标而绕过 action gate。
- 当前 v1 split 还不能直接使用：必须先补充或构造经许可/审核的 benign 训练来源，定义每个训练角色的最低 benign 支持量，并在新数据版本中确保 train/validation/calibration/test_a 均有足够正负样本；只把现有 39 条 benign 重新分配不能支持稳定的 1% FPR。

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
- 当前 validation 只有攻击样本，不能用于模型选择；C-only-smoke 如获批准，只能使用明确标记为工程 fixture 的平衡小样本验证代码路径，不能把其损失或准确率写成真实数据结果。

## 项目所有者需要确认的决定

在真实 `dataset_statistics.json` 生成并复核后，项目所有者应在本文件记录：

- 选择：`A` / `B` / `C-only-smoke`；
- 决定日期与决定人；
- 是否批准新协议版本；
- 是否批准动作构造与独立审计阶段；
- 若涉及外部模型或新增数据，许可、下载范围与预算边界。

在上述字段未确认、且所选路线的数据前置条件未通过前，状态保持 `C1_EVIDENCE_VALIDATED_TRAINING_BLOCKED`，正式模型训练入口关闭。
