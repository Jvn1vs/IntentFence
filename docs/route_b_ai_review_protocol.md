# Route B 双 AI 工程审核协议（草案）

## Material Passport

- Origin Skill: Academic Research Suite / experiment-agent
- Mode: engineering evidence protocol revision
- Prepared: 2026-08-26
- Status: `AI_REVIEW_DIRECTION_APPROVED_CONSTRUCTION_AUTHORIZED_NOT_TRAINING_AUTHORIZED`
- Protocol version: `2.1.0-ai-draft.1`
- Parent: `2.0.0-draft.2` human-review draft

## 1. 适用范围和证据等级

项目所有者选择工程/简历演示路线后，双 AI 审核可以替代当前 C1B 的人工审核流程，
但不会产生独立人类审核证据。所有输出必须标记为 `ai_reviewed_engineering_only`；
`human_verified` 永远保持 `false`，`formal_training_authorized` 也保持 `false`。

这条路线可用于工程冒烟、数据管线演示、简历中的“构建并验证了双 AI 审核框架”等
表述，不可表述为“人工验证数据”或论文级标签质量证据。

## 2. 双 AI 独立性要求

需要两个不同的 AI 审核执行单元。至少 provider、model 和 revision 三者组成的身份
必须不同；每个执行单元都使用温度 `0`、固定 prompt 哈希，并且看不到 seed labels、
另一个 AI 的输出和预设答案。可以是项目所有者选择的不同外部 AI，也可以是两个本地
模型；Codex 不会自动调用或上传语料。

每个 AI 的 metadata 必须记录 provider、model、revision、prompt SHA-256、温度、执行
模式、原始输出文件 SHA-256 和是否得到项目所有者的外部上传批准。只保存结构化标签
和必要的短备注，不要求或保存隐式思维链。

项目所有者的持续操作偏好（2026-08-30）：凡由 Codex 执行的 C1B 审核，默认且必须使用
恰好两个相互独立的模型；不得将单模型输出作为双审结论，也不得在结果不理想时临时增加模型
以挑选有利结论。额外模型只能按预先声明的补充协议产生独立的 AI 工程证据。

## 3. 审核任务

两套审核仍使用现有盲审包中的 400 条 Risk 和 400 条 Alignment/action。Risk 只根据
`untrusted_content` 标注五分类；Alignment 根据 `user_goal`、`untrusted_content` 和
`proposed_action` 标注四分类，并单独标注 action realism。完整标签定义见
[`route_b_ai_audit_rubric.md`](route_b_ai_audit_rubric.md)。旧
[`route_b_audit_rubric.md`](route_b_audit_rubric.md) 只保留给历史人类审核草案。

两个 AI 都必须独立输出与原 CSV 相同的固定列。不可编辑的样本字段必须逐字保留，不能
重排、删行或补造样本。审核 CSV 的 `sample_id` 必须是不可逆的、标签中性的 audit ID，
不得暴露源 `sample_id`、Risk 或 Alignment 种子标签；源 ID 的映射只能留在
`sealed_seed_labels.json`。

## 4. 分析和质量门

Codex 只校验 CSV 的不可变字段、metadata、输入/输出哈希和双 AI 一致性；同时计算
Risk/Alignment 的原始一致率、Cohen's kappa、逐类一致率和 action realism。与 candidate
构造标签的 agreement 只能称为 `construct agreement`，不能称为 ground-truth accuracy。

当前质量门沿用 0.95 完成率、0.90 原始一致率、0.80 Cohen's kappa、0.90 逐类一致率和
0.95 realistic 比例。失败时标记 AI 工程证据失败，不覆盖、不手工调高结果。

即使质量门全部通过，报告仍应包含：

- `review_mode=dual_ai_engineering`；
- `human_verified=false`；
- `formal_training_authorized=false`；
- AI provider/model/revision、prompt 和原始输出哈希；
- AI 共同偏差、模板泄漏、外部上传和模型版本漂移的限制说明。

## 5. 明确不做的事

- 不把两个 AI 当作两名人类审核者；
- 不把 AI 输出写入 `human_verified=true`；
- 不因 AI 质量门通过而自动启动训练、校准或最终测试；
- 不把未公开语料发送给外部服务，除非项目所有者另行确认 provider 条款和上传范围；
- 不提交原始 CSV、seed labels、候选数据、外部 AI 响应缓存或凭据。
