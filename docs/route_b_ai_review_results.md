# Route B 双 AI 工程审核结果

状态：`ai_reviewed_engineering_only`；本记录接受预注册质量门未通过的负结果。

## 证据边界

本记录只汇总工程审核指标，不构成人工审核、ground-truth accuracy、正式训练授权或最终测试授权。两次运行均保持：

- `human_verified=false`；
- `formal_training_authorized=false`；
- 不修改 seed labels、CSV 标签或预注册阈值；
- 原始 CSV、seed labels、JSON 报告和凭据留在本地忽略目录，不提交仓库。

## 运行汇总

| 运行 | AI B | 主要结果 | 失败质量门 |
|---|---|---|---|
| Kimi K3 | WorkBuddy / `kimi-k3` | Risk 完成 400/400；Alignment 原始一致率 0.9675，Cohen’s κ 0.9567；13 条 Alignment 分歧 | Alignment `malicious` seed agreement 0.87 |
| DeepSeek V4 Flash | DeepSeek / `deepseek-v4-flash` | Alignment 完成 400/400，原始一致率 1.0，Cohen’s κ 1.0；Risk 原始一致率 0.9025，Cohen’s κ 0.8781；39 条 Risk 分歧 | Risk `instruction_hijacking` seed agreement 0.5125 |

两次运行均为 `ai_quality_gates_failed_engineering_only`。Kimi K3 的分歧集中在 Alignment 的恶意类边界；V4 Flash 的分歧集中在 Risk 的指令劫持类边界。该差异说明模型对合成审核构造的类别边界存在系统性不同，不能通过继续挑选模型或事后调阈值来宣称通过。

## 接受的结论

Route B 双 AI 路线可作为“实现并验证了双 AI 审核框架、并记录了可复现负结果”的工程/简历材料。不能表述为人工验证数据、论文级标签质量证据或训练前授权证据。后续如需更强证据，必须另行预先声明新的 provider/model/revision、Prompt、数据包和评价规则，并保留本次失败结果。
