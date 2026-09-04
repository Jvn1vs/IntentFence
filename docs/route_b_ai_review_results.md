# Route B 双 AI 工程审核结果

状态：`ai_reviewed_engineering_only`；本记录保留历史失败运行，并新增 GLM5.2 替代运行结果。
2026-09-04 起，冻结的 `2.2.0-ai-assisted-engineering.1` 允许将结构上有效的双 AI 结果
用于项目所有者风险接受后的工程训练；本记录中的失败质量门仍不可改写，且不产生人类审核、
formal training 或最终测试证据。

当前 2.2.0-ai-assisted-engineering.1 readiness 绑定的具体包只有：

- AI manifest/四张提交表：
  data/interim/route_b_v2_candidate_8_human_audit_v2_ai_pair/；
- 对应的 audit manifest/封存 seed labels：
  data/interim/route_b_v2_candidate_8_ai_pair_audit/；
- 分析文件：
  data/interim/route_b_v2_candidate_8_human_audit_v2_ai_pair/ai_review_analysis.json。

文档后续列出的 candidate 8 其他双 AI 运行仍是历史补充证据，不会被新路线的 readiness
隐式混用；每个运行都必须以自己的 manifest、audit manifest 和分析文件绑定。

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
| GLM5.2（替代运行） | WorkBuddy / `glm-5.2` | Risk 完成 400/400，原始一致率 1.0，Cohen’s κ 1.0；Alignment 完成 400/400，原始一致率 0.98，Cohen’s κ 0.9733；8 条 Alignment 分歧已由项目所有者裁决 | 数值质量门均通过；裁决只关闭工程分歧，不构成人类双审或正式训练授权 |

前两次历史运行均为 `ai_quality_gates_failed_engineering_only`。Kimi K3 的分歧集中在 Alignment 的恶意类边界；V4 Flash 的分歧集中在 Risk 的指令劫持类边界。该差异说明模型对合成审核构造的类别边界存在系统性不同，不能通过继续挑选模型或事后调阈值来宣称通过。

GLM5.2 替代运行的所有数值质量门均通过，Alignment 的 `malicious` 逐类 seed agreement 为 0.92；分析器在原始运行阶段因 8 条与 AI A 的分歧而保留 `ai_quality_gates_failed_engineering_only`。项目所有者随后通过独立裁决文件关闭了这 8 条工程分歧，但没有改写原始分析结果。该结果只能作为一致性工程证据，不能替代独立人工审核。

## 人工裁决记录

项目所有者已对这 8 条分歧完成裁决：最终标签均为 `ambiguous`，审核者为 `zjx`，裁决时间为
`2026-08-27T23:08:00+08:00`。裁决表及其独立 JSON 记录保存在本地忽略目录；原始 AI CSV、
AI manifest 和 AI 分析 JSON 未被覆盖。该记录解决了当前 AI 分歧，但不等同于两名独立人类审核，
因此 `human_verified=false` 与 `formal_training_authorized=false` 继续保持。

## 接受的结论

Route B 双 AI 路线可作为“实现并验证了双 AI 审核框架、并记录了可复现负结果”的工程/简历材料。不能表述为人工验证数据、论文级标签质量证据或训练前授权证据。后续如需更强证据，必须另行预先声明新的 provider/model/revision、Prompt、数据包和评价规则，并保留本次失败结果。

## Candidate 6 重新审核状态

上述全部结果只绑定 candidate 4。Small A 运行后发现 candidate 4 的归一化语义模板跨
train/validation 重用，因此旧审核不能转移到修复后的 candidate 6。

candidate 6 的首个盲审包 `audit_v1` 随后被发现其 reviewer-facing `sample_id` 含有 Risk 和
Alignment 种子标签，违反标签隐藏要求；未提交审核结果，已保留为失效证据，不得用于分析。
生成器已修复并重新生成 `data/interim/route_b_v2_candidate_6_audit_v2`：四张表各自保留 400
行，所有 reviewer-facing ID 均为标签中性的 `audit-{task}-{hash}`，manifest 自哈希为
`2c33e389c061461cfccdadf1808969abe9bf6c1176c4cb5cdd76312682b54232`。当前状态仍为待由两个未
接触 `audit_v1` 的独立 AI 重新审核；`human_verified=false`、`formal_training_authorized=false`。

首次派发 AI B 时还发现旧 `route_b_audit_rubric.md` 是历史人类审核文件，包含“AI 不可担任
reviewer B”的遗留约束；AI B 因此正确停止且没有改动审核表。活动双 AI 协议现绑定独立的
`route_b_ai_audit_rubric.md`，历史人类说明保持不变。

## Candidate 6 `audit_v2` 双 AI 运行

AI A 为 OpenAI Codex `gpt-5.6-sol`，AI B 为 OpenAI Codex `gpt-5.6-terra`；两者均使用本地
执行模式、温度 0、不同模型身份，且分别声明未见种子标签和对方输出。四张 CSV 均为 400/400
完成，所有 action realism 判断为 `realistic`。输入、不可编辑字段、CSV 哈希和双 AI manifest
均通过验证，未发现 package validation error。

AI A 在活动协议仍错误指向历史 human rubric 时完成；该文件的 Risk/Alignment 标签定义和质量门
与后续 AI rubric 相同，但 reviewer-role 文字冲突已如上记录。AI B 的首次任务因此停在写入前，
在新增 AI rubric 后以新的固定 prompt 恢复。两位审核者的不同 prompt SHA-256 均已写入 manifest；
这项修复不追溯改写 A 的原始 CSV，也不改变任何标签或预注册门槛。

该运行仍为失败的工程证据：Risk 原始一致率为 0.8925，低于预注册的 0.90；Risk Cohen's κ 为
0.8499，但 Risk 逐种子类别 construct agreement 未通过。Alignment 的双 AI 原始一致率和 κ
均为 1.0，但两位 AI 对 seed `ambiguous` 类的 construct agreement 都为 0，因此 Alignment
逐类质量门同样未通过。最终状态为 `ai_quality_gates_failed_engineering_only`。

这不是模型性能结论，也不允许通过改标签、修改门槛、挑选运行或启动训练来“修复”。原始 CSV、
metadata 和分析 JSON 均保存在忽略目录；`human_verified=false`、
`formal_training_authorized=false` 保持不变。

## Candidate 7 `audit_v1` 双 AI 运行

candidate 7 以 candidate 6 的失败诊断为输入，**只**重新表述合成构造：`instruction_hijacking`
不再同时要求数据外送、权限变更或工具替换，`tool_manipulation` 只替换同一工具调用中的公开对象，
并把一个真实的未获授权操作保留为 Alignment `ambiguous`。冻结的标签、抽样种子、审核行数和
预注册门槛均未作事后修改。四个 split 共 27,000 条记录仍通过 manifest、精确重复、近重复、
归一化文本模板和动作模板隔离检查。

AI A 为 OpenAI Codex `gpt-5.6-sol`，AI B 为 OpenAI Codex `gpt-5.6-terra`；均为本地执行、
温度 0、不同模型身份，并分别声明未见封存 seed labels 或对方输出。candidate 7 审核包 manifest
文件 SHA-256 为 `3d6de4cd027bb23afa4f296f37613a58a34806ace9920ab8fcce245302a5e9d0`；每位审核者均完成
400 条 Risk 与 400 条 Alignment，零弃审，包与输出哈希验证均通过。

数值质量门全部通过：Risk 原始一致率为 0.9875、Cohen's κ 为 0.9844；Alignment 原始一致率为
0.985、Cohen's κ 为 0.98；Risk 的逐 seed-class agreement 最低为 0.9375，Alignment 最低为
0.94，且 action realism 为 1.0。原始输出仍有 5 条 Risk 和 6 条 Alignment 分歧；因此分析器按
冻结规则返回 `ai_quality_gates_failed_engineering_only`（并非数值门失败，而是不得把未裁决分歧
伪装为无争议通过）。A/B 原始 CSV 不会被改写。

已依照补充协议生成独立的第三 AI 全量 400 条 Alignment 盲审包（包 manifest SHA-256 为
`19ae616da1d617636e0a6a874f9717bd52e35c899790f953117ffd74467e4876`）。它只提供补充一致性
证据，不能覆盖 A/B 的原始状态，也不能替代项目所有者的独立人工裁决。candidate 7 继续保持
`human_verified=false` 和 `formal_training_authorized=false`。

第三 AI（OpenAI Codex `gpt-5.6-luna`）已完成该完整 400 行包，格式、固定字段、身份、时区
时间戳、包哈希和输出哈希均通过核验，且零弃审。它给出 102 `aligned`、200 `unrelated`、98
`malicious`，并给出 388 `realistic`、12 `unrealistic`。与封存构造标签相比，第三 AI 的
`aligned` 与 `unrelated` 逐类 agreement 均为 1.0，`malicious` 为 0.98，而全部 100 个
`ambiguous` 被独立判为 `unrelated`，该类 agreement 为 0，整体 construct agreement 为 0.745。
因此第三 AI 的补充质量门失败，且必须保留 A/B/C 全部原始意见。12 条 `unrealistic` 均为
`ticket.update` 使用 wildcard `ticket_id="*"` 的候选动作；这是一项可复现的 mock-action
现实性构造风险，而非对训练模型的测量。

## Candidate 8 `audit_v1` 双 AI 运行

candidate 8 仅处理 candidate 7 第三 AI 揭示的一个可复现构造问题：新增了按 scenario ID 覆盖
action template 的配置机制，并把 `ticket_status` 与 `project_update` 中 destructive
`ticket.update` 的 wildcard `ticket_id="*"` 替换为场景中明确的具体 ticket ID。candidate 7、
其审核包和原始输出保持冻结。candidate 8 的 27,000 条 project-owned mock 语料已通过 manifest、
结构、近重复和归一化文本/动作模板隔离检查；四个 split 的数量与 Risk/Alignment 配比不变。

OpenAI Codex `gpt-5.6-sol` 与 `gpt-5.6-terra` 各自完成 400 条 Risk 和 400 条 Alignment，零弃审。
审核 CSV、盲审包和最终 manifest 的哈希与固定字段均通过验证。Risk 为完全一致（原始一致率 1.0、
κ 1.0，所有逐类 construct agreement 1.0）；Alignment 原始一致率为 0.9775、κ 为 0.97，逐类
construct agreement 最低为 0.95，action realism 为 1.0。所有预注册数值质量门通过，且两名审核者
均将所有 400 条 Alignment 动作判为 `realistic`，说明 wildcard 修复解决了上一轮所报告的现实性
问题。

Alignment 原始输出仍有 9 条分歧，冻结分析器因而返回
`ai_quality_gates_failed_engineering_only`；这是“分歧待独立裁决”的 fail-closed 结果，不是数值
门失败。A 的原始 metadata 曾将本地执行表示为 `local: false` 且缺少标准 `execution_mode` 字段；
原文件未被修改，A 随后单独提交了带哈希的 local-execution attestation，最终 manifest 同时绑定
原 metadata 和该补充证明。这一记录不能消除 9 条语义分歧，也不改变
`human_verified=false` 与 `formal_training_authorized=false`。

项目所有者随后完成了这 9 条 Alignment 分歧的独立裁决：全部最终为 `ambiguous`，裁决人登记为
`zjx`，每行均有带时区的时间和理由。原始 AI CSV、生成时的待裁决包 manifest 与其 source hashes
均未改写；填写后的表因表格软件使用 `gb18030` 保存，已用该编码核验，并由独立 submission receipt
绑定其 SHA-256。该裁决只关闭 candidate 8 已记录的 AI 分歧；原始分析仍保留为
`ai_quality_gates_failed_engineering_only`，且不构成独立人类双盲审核或正式训练授权。

## Candidate 8 补充双 AI 运行

按项目所有者指示，另以新的标签中性盲审包执行补充双 AI 审核；该包与仍待真实人类审核的包
分目录保存，补充审核者为 OpenAI `gpt-5.5` 与 `gpt-5.4`，均为本地执行、温度 0、各完成 400 条
Risk 与 400 条 Alignment、零弃审，且不接触封存标签或对方输出。Risk 完全一致（原始一致率与
κ 均为 1.0）；Alignment 原始一致率为 0.995、κ 为 0.9933，逐类 construct agreement 最低为 0.98，
action realism `realistic` 比例为 0.99875。所有预注册数值门通过。

原始 Alignment 输出仍有 2 条标签分歧，另有一名审核者将 1 条动作标为 `unrealistic`；因此该
补充运行同样为 `ai_quality_gates_failed_engineering_only`。这条新证据不会覆盖 candidate 8 的
既有 AI 运行、项目所有者的 9 条裁决或仍待的人类双盲审核；`human_verified=false` 与
`formal_training_authorized=false` 继续保持。

## Candidate 8 人工 v2 包的双 AI 补充审核（2026-08-31）

按项目所有者的新操作规则，使用两个独立 Codex 模型对与人工 v2 包相同抽样内容的 AI-only
派生包分别审核：OpenAI `gpt-5.5` 与 `gpt-5.4`，均为本地执行、温度 0，分别完成 400 条
Risk 与 400 条 Alignment。人工 v2 原包、空白 attestation 和封存 seed labels 未被修改。
可公开聚合诊断见 `reports/data_quality/route_b_candidate_8_human_v2_ai_pair_failure.md`。

派生 AI 包结构校验通过且无 validation error，但预注册质量门失败：Risk 原始一致率为
0.80、Cohen's κ 为 0.75，最低逐 seed-class construct agreement 为 0；Alignment 原始
一致率为 0.8575、κ 为 0.81，最低逐 seed-class construct agreement 为 0.51；action
realism 为 0.99875。Risk 的唯一 80 条 A/B 分歧是 A 的 `instruction_hijacking` 与 B 的
`tool_manipulation` 之间的边界；Alignment 共 57 条分歧。该运行最终状态为
`ai_quality_gates_failed_engineering_only`，只能作为 AI 工程负证据，不能替代独立人类双盲
审核、设置 `human_verified=true`、打开 `formal_training_authorized` 或启动训练。
