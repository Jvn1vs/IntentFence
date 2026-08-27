# Route B 双 AI 工程审核手册

状态：`2.1.0-ai-draft.1`；工程/简历演示路线；不产生论文级人工标签证据。

## 0. 先确认边界

这条路线使用两个不同的 provider/model/revision。Codex 不会自动调用 AI，也不会把项目
语料上传到外部服务。若使用外部 AI，项目所有者必须先确认 provider 条款和上传范围，
并在 `ai_review_manifest.json` 中记录批准。`human_verified` 和
`formal_training_authorized` 永远为 `false`。

## 1. 给两个 AI 的输入

沿用现有目录：

```text
data/interim/route_b_v2_candidate_4_audit_v2/
```

AI A 使用 `reviewer_a_risk.csv` 和 `reviewer_a_alignment.csv`；AI B 使用对应的
`reviewer_b_*.csv`。不要给任何 AI `sealed_seed_labels.json`，也不要让它看到另一个
AI 的输出。每个 AI 需要完成 400 条 Risk 和 400 条 Alignment/action。

将 [`route_b_ai_review_prompt.md`](route_b_ai_review_prompt.md) 分别交给两个 AI。要求
输出完整 CSV，保留固定列，只填写标签和审核元数据；不要输出思维链，不执行动作。

## 2. 登记 metadata

复制 [`route_b_ai_review_manifest.example.json`](../configs/route_b_ai_review_manifest.example.json)
到审核目录，命名为 `ai_review_manifest.json`，替换所有 `REPLACE` 占位符：

- 两个 provider/model/revision 必须不同；
- 温度必须为 `0`；
- 记录 prompt SHA-256；
- 记录四份提交 CSV 的 SHA-256；
- 记录 `audit_manifest.json` 的 SHA-256；
- 若使用外部 AI，把 `external_upload_approved_by_project_owner` 改为 `true`，并确认
  两个 reviewer 的 `execution_mode` 为 `external`。

## 3. 运行分析

```powershell
& $IntentFencePython scripts/analyze_route_b_ai_reviews.py `
  --reviewer-a-risk data/interim/route_b_v2_candidate_4_audit_v2/reviewer_a_risk.csv `
  --reviewer-b-risk data/interim/route_b_v2_candidate_4_audit_v2/reviewer_b_risk.csv `
  --reviewer-a-alignment data/interim/route_b_v2_candidate_4_audit_v2/reviewer_a_alignment.csv `
  --reviewer-b-alignment data/interim/route_b_v2_candidate_4_audit_v2/reviewer_b_alignment.csv `
  --sealed-seed-labels data/interim/route_b_v2_candidate_4_audit_v2/sealed_seed_labels.json `
  --audit-manifest data/interim/route_b_v2_candidate_4_audit_v2/audit_manifest.json `
  --ai-review-manifest data/interim/route_b_v2_candidate_4_audit_v2/ai_review_manifest.json `
  --output data/interim/route_b_v2_candidate_4_audit_v2/ai_review_analysis.json
```

成功时状态为 `ai_quality_gates_passed_engineering_only`。这只表示两个 AI 在固定样本上
达到预注册一致性门，不表示 ground-truth accuracy，也不打开正式训练或最终测试。

## 4. 失败处理

哈希漂移、固定列被修改、身份重复、seed labels 暴露、外部上传未批准或质量门失败时，
报告必须保持失败状态。保留原始 CSV 和原始 AI 结构化输出，不手工修改结果来提高一致率。

## 5. 第三个 AI 补充审核

如果项目所有者要增加一个独立 AI，使用 `scripts/build_route_b_third_ai_package.py` 生成
`data/interim/route_b_v2_candidate_4_audit_v3_third_ai/`。第三个 AI 必须审核完整 400 条
Alignment，而不是只审核既有 13 条分歧。它是补充证据，不是事后裁判；原双 AI 失败结果、
`human_verified=false` 和 `formal_training_authorized=false` 必须保留。

第三个 AI 使用不同的 provider/model/revision、温度 0、独立 prompt；不能看到 AI A/B 输出
或 `sealed_seed_labels.json`。第三个 AI 的结果只能按补充协议
`configs/route_b_ai_review_protocol_third.yaml` 解释，不能自动把原质量门改为通过。
