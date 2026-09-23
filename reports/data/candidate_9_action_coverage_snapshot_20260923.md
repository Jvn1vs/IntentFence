# Candidate 9 动作与标签证据快照（2026-09-23）

本快照只读取已批准的本地 train/validation 和隔离来源清单；没有读取 calibration、Test A/B/C/D 内容或模型预测。计数描述现有**证据状态**，不把 AI 暂定意见当正式训练标签。

| 来源 / 固定输入 SHA-256 | 规模 | 可主张的证据 | 不能主张的内容 |
|---|---:|---|---|
| candidate 9 v3 train `57294e964d5aec1306b813442c26834d1e318cf6dcba2b7b09570388275e4576`、validation `269efb4d15cfdeaccce67730937d918374163dfb7add7ab46aade83baecd44d0` | 14,582 + 2,065 = 16,647 行 | 暂定 benign 4,170、instruction_hijacking 12,477 | 每行 `proposed_action` 是空字符串、`adapter_missing_action=true`、`action_provenance=missing`；Task Alignment 均缺，human_verified=0。不能把字段存在误计为动作。 |
| AIB AI 场景清单 `259689b354db7405e8aa63740f717db0f94b5b5d71502858e8886f476f08982a` | 182 场景 | AI 暂定 Risk：data_exfiltration 73、benign 40、privilege_escalation 34、tool_manipulation 25、instruction_hijacking 10 | 正式 Risk/Alignment 标签均为0；场景描述不是实际代理动作。 |
| AIB v3 动作登记册 `d2a4fbf34d9d06df13a94a236a8e211a6081cd8f6d93473533ed7a60f3a7d5fd` | 25 动作、15 场景；10个双动作场景和5个单动作场景 | 所有动作有 `sandbox_policy_output` 来源与可重放离线观测；15场景的 AI 暂定 Risk 覆盖五类（4/4/3/2/2，顺序见下） | 25条均 `model_generated=false`，正式 Risk/Alignment/split 为空，human_verified/training_ready=false；不证明自主代理执行或合格动作配对。 |
| ToolSafety 200条 AI 预审 `64e99ef6ebc4b9c9e53a1c86e920a9ca1f843a576c6c2a916432c2bb2a4d00c4` | 200 动作前缀 | 原始暂定 Risk 全 benign；Alignment aligned 112、ambiguous 86、unrelated 2；三条定向复核中一条旧 unrelated 改为 ambiguous | 预审未独立人审，正式 Alignment 均为0。三条目标的辅助定义归属未闭合，不能作训练覆盖。 |

AIB 15个已形成动作的场景，AI 暂定 Risk 分布为 data_exfiltration 4、benign 4、instruction_hijacking 3、tool_manipulation 2、privilege_escalation 2。其中10个双动作场景分别为 instruction_hijacking 3、privilege_escalation 2、tool_manipulation 2、data_exfiltration 2、benign 1；五个单动作场景为 benign 3、data_exfiltration 2。这只说明工程准备的范围，不说明同一内容下已拥有两种**经审核且不同的 Alignment**。来源族/保护集语义隔离也未完成，不能据此生成角色拆分。

当前五类 Risk 只有“场景层 AI 暂定覆盖”；四类 Alignment 没有一类正式可用，更没有各内部角色五类/四类齐全的证据。下一步优先核查已形成的同前缀双动作能否通过独立语义审核，特别是正常内容但动作 `unrelated` / `ambiguous` 的反例；缺少时继续找有工具参数和授权边界的公开动作来源。When2Call 仍是待具体授权的只读提案，不能纳入本快照。训练、校准与正式最终测试门不变。
