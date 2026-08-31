# Route B 双 AI 工程审核手册

状态：`2.1.0-ai-draft.1`；工程/简历演示路线；不产生论文级人工标签证据。项目所有者已
确定：Codex 执行审核时默认使用恰好两个相互独立的模型。

## 0. 先确认边界

这条路线使用两个不同的 provider/model/revision。Codex 不会自动调用 AI，也不会把项目
语料上传到外部服务。若使用外部 AI，项目所有者必须先确认 provider 条款和上传范围，
并在 `ai_review_manifest.json` 中记录批准。`human_verified` 和
`formal_training_authorized` 永远为 `false`。

## 1. 给两个 AI 的输入

candidate 6 为历史失败审核证据；当前候选为 candidate 8。candidate 8 已完成两轮双 AI
审核，原始输出与补充输出均已封存，因此不得对现有目录重跑或覆盖。今后生成新的候选审核包时，
使用标签中性的 audit 目录，并保持两个模型彼此不可见。

```text
data/interim/route_b_v2_candidate_8_audit_v1/
```

candidate 6 的旧 `audit_v1` 曾暴露标签，已失效；后续所有审核包均使用标签中性的
`audit-{task}-{hash}` 标识符。

candidate 8 的初始审核包 `audit_manifest.json` 文件 SHA-256 为
`d292d0c988908e5d8812ebb9814705c738630f2d4fe3bec95e9fbc7bc34c9fa5`；填写
`ai_review_manifest.json` 的 `audit_manifest_sha256` 时始终使用文件哈希，而不是 self-hash。
candidate 4、6 和 7 的审核包及结果只作为历史证据保留，不能转移到 candidate 8。

为新的候选构建双 AI 包时，必须显式指定 AI 模式；不要使用人类签核包或其 provenance 模板：

```powershell
& $IntentFencePython scripts/build_route_b_blind_audits.py `
  --input <candidate_dir>/train.jsonl `
  --input <candidate_dir>/validation.jsonl `
  --input <candidate_dir>/calibration.jsonl `
  --input <candidate_dir>/test_a.jsonl `
  --output-dir <new_dual_ai_audit_dir> `
  --risk-rows 400 --alignment-rows 400 --seed <frozen_seed> `
  --review-mode dual_ai_engineering
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
  --reviewer-a-risk data/interim/route_b_v2_candidate_6_audit_v2/reviewer_a_risk.csv `
  --reviewer-b-risk data/interim/route_b_v2_candidate_6_audit_v2/reviewer_b_risk.csv `
  --reviewer-a-alignment data/interim/route_b_v2_candidate_6_audit_v2/reviewer_a_alignment.csv `
  --reviewer-b-alignment data/interim/route_b_v2_candidate_6_audit_v2/reviewer_b_alignment.csv `
  --sealed-seed-labels data/interim/route_b_v2_candidate_6_audit_v2/sealed_seed_labels.json `
  --audit-manifest data/interim/route_b_v2_candidate_6_audit_v2/audit_manifest.json `
  --ai-review-manifest data/interim/route_b_v2_candidate_6_audit_v2/ai_review_manifest.json `
  --output data/interim/route_b_v2_candidate_6_audit_v2/ai_review_analysis.json
```

成功时状态为 `ai_quality_gates_passed_engineering_only`。这只表示两个 AI 在固定样本上
达到预注册一致性门，不表示 ground-truth accuracy，也不打开正式训练或最终测试。

## 4. 失败处理

哈希漂移、固定列被修改、身份重复、seed labels 暴露、外部上传未批准或质量门失败时，
报告必须保持失败状态。保留原始 CSV 和原始 AI 结构化输出，不手工修改结果来提高一致率。

## 5. 第三个 AI 补充审核

如果项目所有者要增加一个独立 AI，使用 `scripts/build_route_b_third_ai_package.py` 从当前
candidate 6 审核包生成新的独立目录。第三个 AI 必须审核完整 400 条
Alignment，而不是只审核既有 13 条分歧。它是补充证据，不是事后裁判；原双 AI 失败结果、
`human_verified=false` 和 `formal_training_authorized=false` 必须保留。

第三个 AI 使用不同的 provider/model/revision、温度 0、独立 prompt；不能看到 AI A/B 输出
或 `sealed_seed_labels.json`。第三个 AI 的结果只能按补充协议
`configs/route_b_ai_review_protocol_third.yaml` 解释，不能自动把原质量门改为通过。

## 6. 项目所有者分歧裁决包

双 AI 数值质量门通过但仍有原始分歧时，可由 Codex **只构造**待项目所有者填写的包；该命令
不会读取或复制 `sealed_seed_labels.json`，不会填入任何最终标签，也不会修改原始 reviewer CSV：

```powershell
python scripts/build_route_b_ai_adjudication_package.py `
  --reviewer-a-alignment data/interim/route_b_v2_candidate_8_audit_v1/reviewer_a_alignment.csv `
  --reviewer-b-alignment data/interim/route_b_v2_candidate_8_audit_v1/reviewer_b_alignment.csv `
  --audit-manifest data/interim/route_b_v2_candidate_8_audit_v1/audit_manifest.json `
  --ai-review-manifest data/interim/route_b_v2_candidate_8_audit_v1/ai_review_manifest.json `
  --output-dir data/interim/route_b_v2_candidate_8_audit_v1_adjudication_v1
```

包内 `alignment_adjudication.csv` 只列出原始分歧与两位 AI 的已提交意见；项目所有者须独立填写
`final_task_alignment_label`、`adjudicator_id`、`adjudicated_at` 和 `rationale`。不得覆盖 A/B
原始文件、不得把 seed labels 填回表中、不得将这项裁决写作双人类盲审，且它本身不改变
`human_verified=false` 或 `formal_training_authorized=false`。

## 7. 历史 candidate 4

`data/interim/route_b_v2_candidate_4_audit_v2/` 及其 Kimi、DeepSeek、GLM 审核与裁决均保留，
但只描述 candidate 4。candidate 4 已发现归一化语义模板跨 train/validation 重用，因此其
Small A 100% validation 结果是数据泄漏负证据，不能作为 candidate 6 的质量或模型证据。
