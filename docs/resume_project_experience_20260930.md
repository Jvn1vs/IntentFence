# IntentFence 简历项目经历草稿

更新日期：2026-09-30。以下“进行中”是计划，不是已取得的实验结果。

## 可直接用于简历

**IntentFence｜面向 LLM Agent 的间接提示注入与动作风险检测（个人研究项目）**
技术栈：Python、PyTorch、Transformers、DeBERTa-v3、FastAPI、Docker

- 设计“用户任务—不可信内容—拟执行动作”联合输入，分别建模五类内容风险和四类任务对齐关系；实现数据 Schema、近重复去重、按场景/模板隔离划分、哈希化来源追踪，以及训练、推理和 Allow / Confirm / Block 策略框架。
- 建立 27,000 条自建离线场景库，并从中使用 5,000 条训练、2,000 条验证样本完成首轮 DeBERTa-v3-base 工程训练（5 个 epoch）；合成验证集 Risk Macro-F1 为 0.9995。通过检查数据构造发现模板化样本可能高估泛化，因此将该结果明确限定为工程验证，不作为真实攻击防御效果。
- 为改善数据单一问题，接入 BIPIA、Dolly 等公开来源，构建并独立校验 20,691 条 candidate 9 候选样本；核查来源许可证、去重与锁定测试集隔离，并从 AgentInjectionBench 形成 25 条带字段来源的离线动作提案，保留未通过语义与标签审核的隔离状态。
- **进行中：**补齐五类风险与四类任务对齐的独立标签和真实参数依据，构建非单一模板的动作对照；完成多随机种子、跨来源评测、误报分析和校准，再验证 ONNX/INT8 导出与 CPU 推理表现。

## 表述依据与边界

- 第一轮训练和 0.9995 是 candidate 8 的 **Risk 五分类合成 validation** 指标，仅 seed 42、一次工程运行；不是 Alignment、最终测试、跨来源泛化或真实防御指标。见 `reports/training/c2b_base_action_multitask_seed42_20260905.md`。
- 27,000 条为 candidate 8 project-owned mock 场景；20,691 条 candidate 9 为构造候选，新增正常背景为主，当前只含暂定 benign / instruction_hijacking，尚无动作与独立 Alignment 标签。见 `docs/project_narrative.md`、`reports/data/candidate_9_v3_build_20260909.md`。
- 25 条 AIB 动作提案来自 15 个场景的离线策略观测，不是模型自主执行；Risk/Alignment 正式标签、split、human_verified/training_ready 均未完成。见 `reports/data/candidate_9_action_coverage_snapshot_20260923.md`。
- FastAPI、策略与导出/量化基建已实现；真实模型 ONNX/INT8、CPU 延迟及最终测试结果尚不存在。见 `README.md` 与 `docs/task_progress_plan.md`。
