# ToolSafety 隔离前缀完整 AI 预审（2026-09-11）

已完成批准范围内 **200/200 条完整动作前上下文 AI 预审**，剩余 0 条。汇总状态为 `ai_reviewed_quarantined`；没有应用训练标签、接入训练或执行来源工具。此次结果不能补齐 candidate 9 缺失的攻击类别。

## 暂定结果与适用性

| 当前内容 Risk | aligned | unrelated | ambiguous | malicious | 合计 |
|---|---:|---:|---:|---:|---:|
| benign | 112 | 2 | 86 | 0 | 200 |
| instruction_hijacking | 0 | 0 | 0 | 0 | 0 |
| data_exfiltration | 0 | 0 | 0 | 0 | 0 |
| privilege_escalation | 0 | 0 | 0 | 0 | 0 |
| tool_manipulation | 0 | 0 | 0 | 0 | 0 |

这里的 benign 只表示 AI 在当前工具返回中未识别出攻击机制，不保证整条轨迹安全、真实或可执行。112 条 aligned 也不等于已合格训练样本。该包从结构合格子集抽样，不按攻击类别分层；不能由零攻击推断原始 ToolSafety 没有攻击，也不能计算模型准确率或声称泛化提升。

主要发现：

1. 默认参数、跨接口 ID 和未提供的用户身份经常影响目标对应关系。15、43 号沿用示例 ID；175 号同一 ID 的商品从搅拌机变成耳机；195 号拼造未返回的 GUID。
2. 信息不足与动作无关需要区分。139 号查询的新闻来源不是已选来源，151 号用随机法语词接口替代指定词翻译，暂定 unrelated。用户预算、地点、兴趣或对象缺失的情形保留 ambiguous。
3. 59 号补写维护费政策、71 号补写职业兴趣、83 号补写活动事实，均与任务主题相关但缺依据。复核后从 unrelated 修正为 ambiguous，保留原意见和修订原因。
4. 接口认证与语义对齐分别判断。90、96 号查询直接支持任务；没有具体越权证据时，不因使用工具定义内默认凭据单独判 ambiguous。原判断及修订也已保留。凭据真实性未外部验证，报告不复制其值。
5. 返回成功不证明真实执行。完整历史中可见嵌套引号、数值/布尔/数组以字符串传入、模拟市场资料等问题。原结构筛查仅证明选定相邻位置满足部分解析要求，未证明全部历史可执行。

这批资料可保留为普通工具流程及动作质量的候选研究材料；不是缺失三类攻击数据的可靠替代，也尚未形成同一内容配不同动作的对照组。

## 抽样、阅读与审核身份

- 固定源：`jinjinyien/ToolSafety`，revision `7c444473e0dc0a822247858c249b10856ade04ef`。
- 在诊断通过且工具定义唯一的 2613 条对话中，以 seed 42 无放回抽取 200 条；每条随机选一个合格位置。
- 原始隔离包：`data/interim/toolsafety_prefix_review_20260911/`。每条含完整系统与工具定义、动作前历史（含当前返回）及拟执行动作，不含其未来结果。
- 最终汇总：`data/interim/toolsafety_full_review_20260911/reviews.jsonl` 与 `manifest.json`。
- 首轮曾完成 200 条局部三字段初筛；随后主审分批完成 43 条完整阅读，三个 agent 分别完成互斥的 53、52、52 条。长输出分段补读；完全相同的共享工具定义经实际相等比较后复用已读内容。
- 主审检查各组意见和成员覆盖，并对标注边界提出复核。该分工不是同一条记录的双独立审核，未计算审核者一致率；所有意见均为 AI/Codex 暂定意见，不是人审。
- 初筛部分视图曾遮蔽凭据样式值，过宽遮蔽的工具名/参数已补看。三个 agent 的完整阅读未脱敏，最终意见和公开报告未复制凭据值。未执行任何源工具。

原始包与初筛、各增量批次保持不变；最新完成数以最终 manifest 为准。原包创建状态 `quarantined_pending_ai_pre_review` 和初筛 verifier 中的 7 条完整阅读计数是历史快照，不代表最终覆盖。

## 可复现证据

| 文件/输入 | SHA-256 |
|---|---|
| 原始源 | `e623a0e72b2faf5270876462dc8a3197967c533b00755a80050187db34bcbd72` |
| 诊断输入 | `e4de8eb3a0fbf43bebb4b7a52663b3931ccf10a75a80a7b05acb50cbbb69a1a7` |
| 阶段批准配置 | `247b3ba891822d800dc4d2889cdec007c6ab9ead55aa32f93ac2c225f5fd463c` |
| `prefixes.jsonl` | `bb978876abb0ced7c2c8dafd51c6fc1902eb542a2296a25ada07fd4410e3121f` |
| 历史 `ai_pre_reviews.jsonl` | `85d44a4dd0bb577d251fbdfa64b68e9b95801a002d9604b17ecb3c84680f7c4e` |
| 最终 `reviews.jsonl` | `64e99ef6ebc4b9c9e53a1c86e920a9ca1f843a576c6c2a916432c2bb2a4d00c4` |
| 最终 `manifest.json` | `2f99c790d912d1a69f71b981ec323f1b5ee3c428c975c70237477653e97fd573` |
| 汇总器实现 | `9ffef266eecd3daa425647216c151964d27e45099c13455bd50431115ffc04d2` |

最终 manifest 另保存全部 9 份完整意见文件及 2 份修订记录的哈希。汇总器先调用原 verifier 重放 200 条抽样和源边界，再拒绝重复、缺失、异源或非法标签，核对历史批次回执及意见绑定。校验通过证明来源与记录可追溯，不证明 AI 语义判断正确。

复现使用 Conda `intentfence`，输出目录须尚不存在：

```powershell
conda activate intentfence
python scripts/aggregate_toolsafety_full_reviews.py --package data/interim/toolsafety_prefix_review_20260911 --output data/interim/toolsafety_full_review_replay --require-complete
```

验证：完整 pytest **312 passed（64.52 秒）**；最终补充修订记录哈希后，相关 16 项测试再次通过；Ruff、compileall、wheel 构建通过。pytest 设置 `OPENBLAS_NUM_THREADS=1`、`OMP_NUM_THREADS=1`。测试覆盖动作未来结果隔离、源篡改拒绝、成员完整性、训练标签边界、重复意见拒绝及 Risk/Alignment 独立保存。

变更包括批准配置、前缀构造/初筛封装/验证/完整汇总四个脚本、两份测试、本报告、进度计划与项目叙事。源数据和逐条意见留在 Git 忽略目录。

## 阶段停止点

本次 200 条隔离预审阶段完成。`human_verified=false`、`training_ready=false`、训练标签为空、`split=null`；上游逐工具归属、锁定集合隔离和独立审核仍未解决。candidate 8 第一轮结果与 candidate 9 v3 保持原状。

建议下一阶段针对 data_exfiltration、privilege_escalation、tool_manipulation 检索具有明确攻击目标、动作证据和可追溯训练划分的来源，先核对条款与测试重叠再决定下载。按项目阶段规则，完成报告和阶段提交后停止，等待所有者确认下一阶段。
