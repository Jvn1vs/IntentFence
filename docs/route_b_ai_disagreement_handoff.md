# Candidate 8 AI 分歧复核交接

这是对 candidate 8 最新双 AI 工程运行的补充项目所有者复核包，不是独立人类 v2 双盲包。
它只用于逐条检查 AI 双方意见分歧，不能替代两名独立人类对完整 400 条 Risk 与 400 条
Alignment 的审核，也不能设置 `human_verified=true`、`formal_training_authorized=true` 或
启动训练。

本次加固后的目录是 `data/interim/route_b_v2_candidate_8_ai_disagreement_adjudication_v2/`。
先前生成的同名 `..._v1/` 包是加固前的未填写临时产物，已被 v2 取代，不应继续填写。

## 输入与生成

AI A/B 的原始 CSV、AI manifest 和分析 JSON 来自
`data/interim/route_b_v2_candidate_8_human_audit_v2_ai_pair/`；对应的 audit manifest 来自
兄弟目录 `data/interim/route_b_v2_candidate_8_ai_pair_audit/`。这些输入均保持不变；封存
seed labels 不会复制到输出。命令使用 Conda 的 `intentfence` 环境；若 `conda` 尚未加入
PATH，请先按 `docs/c1_user_runbook.md` 的预检块解析该环境。
使用以下命令生成一个不可覆盖的复核目录：

```powershell
conda run -n intentfence python scripts/build_route_b_ai_disagreement_package.py build `
  --reviewer-a-risk data/interim/route_b_v2_candidate_8_human_audit_v2_ai_pair/reviewer_a_risk.csv `
  --reviewer-b-risk data/interim/route_b_v2_candidate_8_human_audit_v2_ai_pair/reviewer_b_risk.csv `
  --reviewer-a-alignment data/interim/route_b_v2_candidate_8_human_audit_v2_ai_pair/reviewer_a_alignment.csv `
  --reviewer-b-alignment data/interim/route_b_v2_candidate_8_human_audit_v2_ai_pair/reviewer_b_alignment.csv `
  --audit-manifest data/interim/route_b_v2_candidate_8_ai_pair_audit/audit_manifest.json `
  --ai-review-manifest data/interim/route_b_v2_candidate_8_human_audit_v2_ai_pair/ai_review_manifest.json `
  --ai-review-analysis data/interim/route_b_v2_candidate_8_human_audit_v2_ai_pair/ai_review_analysis.json `
  --output-dir data/interim/route_b_v2_candidate_8_ai_disagreement_adjudication_v2
```

初始输出包含 README、adjudication manifest 和两张表：

- `risk_disagreement_adjudication.csv`：只列 AI Risk 标签不一致的行；
- `alignment_disagreement_adjudication.csv`：列 AI Alignment 标签或 action realism 不一致的行。

每张表保留不可编辑的样本字段和双方 AI 意见。项目所有者只填写 `final_*`、
`adjudication_status`、`adjudicator_id`、`adjudicated_at` 和 `rationale`。最终 Risk 必须使用
五类 Risk 标签；最终 Alignment 必须使用 `aligned`、`unrelated`、`ambiguous`、`malicious`，
并填写 `realistic` 或 `unrealistic`。时间必须是带时区的 ISO 8601，理由不能为空。

## 完成后验证

保存原始副本后，运行以下命令生成不可覆盖的 submission receipt：

```powershell
conda run -n intentfence python scripts/build_route_b_ai_disagreement_package.py validate `
  --package-dir data/interim/route_b_v2_candidate_8_ai_disagreement_adjudication_v2
```

验证器会拒绝固定字段、AI 意见、行数或源文件哈希漂移，也会拒绝缺少最终标签、理由、
稳定裁决人 ID 或带时区时间的表格。receipt 始终保留
`human_verified=false` 与 `formal_training_authorized=false`；正式人类 v2 双盲包
`data/interim/route_b_v2_candidate_8_human_audit_v2/` 不得被修改。
