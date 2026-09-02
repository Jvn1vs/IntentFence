# Candidate 8 人工双盲审核交接

当前可提交审核包位于 `data/interim/route_b_v2_candidate_8_human_audit_v2/`，只供两名独立人类审核者使用。
它与此前 AI 工程审核输出隔离，使用抽样 seed `20260830`，并保留
`human_verified=false` 与 `formal_training_authorized=false`。

## 分发范围

- 审核者 A：`reviewer_a_risk.csv`、`reviewer_a_alignment.csv`、`reviewer_a_attestation.json`；
- 审核者 B：`reviewer_b_risk.csv`、`reviewer_b_alignment.csv`、`reviewer_b_attestation.json`；
- 两人可使用历史人工 rubric：`docs/route_b_audit_rubric.md`；
- 不得提供 `sealed_seed_labels.json`、`audit_manifest.json`、任何 candidate 6/7/8 AI CSV、
  AI 分析 JSON、AI 裁决表或训练材料。

## 填写规则

每位审核者只能修改本人的两张 CSV 中审核字段，不能改表头、行顺序或样本内容：

- Risk：`risk_label_review`、`review_status`、`reviewer`、`reviewed_at`、`notes`；
- Alignment：`task_alignment_label_review`、`action_realism_review`、`review_status`、
  `reviewer`、`reviewed_at`、`notes`。

审核者须使用稳定匿名 ID 和带时区 ISO 8601 时间。`unable_to_determine` 必须在 `notes`
说明原因。提交后不得改写对方文件，原始 CSV 将由 Codex 做哈希、固定字段、完成率和一致性核验。

每位审核者还须仅填写自己的 attestation JSON：`reviewer_id` 必须与两张 CSV 完全一致，
`reviewer_kind` 保持 `independent_human`，将 `independence_declared` 设为 `true`，并填写带
时区的 `attested_at`。这是 provenance 声明与聚合时的 fail-closed 校验；模型输出不能填写
该声明或作为人类审核提交。

两名审核者交回文件后，项目所有者先运行只读进度检查：

```powershell
conda activate intentfence
python scripts/check_route_b_human_audit_progress.py
```

只有当输出中的 `status` 为 `ready_for_deterministic_aggregation` 时，才运行下面 handoff
所列的确定性分析命令。该检查不读取 `sealed_seed_labels.json`，不生成输出文件，也不会改变
`human_verified` 或 `formal_training_authorized`。

## 当前状态

最新复查（2026-09-02）：四张表均为 400 行，但完整审核为 `0/400`；审核字段和 reviewer-facing
字段仍为空。两份 attestation 的 `reviewer_id` 为空、`independence_declared=false`，仍要求
独立人类声明。v2 包 manifest 的封存 SHA-256 为
`a19eb4430eb3b747073fa980ae0f7bf6afb76da3818f72134df270a5b19fc600`。此前的 v1 包未填写，
仅因缺少此 provenance 证据而保留为不可提交的历史包，不会被覆盖。完成这项审核仍不自动授权
训练；项目所有者须先确认独立人类审核与任何分歧裁决均已完成。
