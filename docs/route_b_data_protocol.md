# IntentFence Route B 训练前数据协议（草案）

## Material Passport

- Origin Skill: Academic Research Suite / experiment-agent
- Mode: reproducibility planning
- Prepared: 2026-08-24
- Evidence cutoff: 2026-08-24
- Status: `DIRECTION_APPROVED_CONSTRUCTION_AUTHORIZED_NOT_FROZEN`
- Parent protocol: `docs/research_protocol.md` version `1.0.0`
- Intended successor: protocol version `2.0.0`，仅在项目所有者批准后冻结

## 1. 已作出的决定与尚未获得的授权

项目所有者已于 2026-08-24 选择 Route B：保留五分类 Risk、独立 Alignment
监督和动作感知输入，并于同日批准协议 `2.0.0` 方向、继续排除尚未单独批准的
CC BY-SA/非商业外部数据，以及项目自有离线 mock-tool 正式候选语料的构造。该决定
授权训练前协议、schema、静态验证器、离线 mock 动作构造和审核材料的开发，但不表示：

- 当前 v1 数据可以训练；
- 已接受任何新增外部数据条款；
- 可以移动、查看模型结果或重新利用 Test A/B/C/D；
- 可以拟合基线、模型权重、温度或阈值；
- Codex 的审核可以冒充独立人工审核。

正式训练入口只有在本协议冻结、v2 manifest 通过、独立人工审核完成且
`formal_training_authorized=true` 后才可能开放；模型训练仍只能由项目所有者执行。

## 2. Route B 的预测目标

### 2.1 Risk：内容风险五分类

`risk_label` 继续使用：

- `benign`
- `instruction_hijacking`
- `data_exfiltration`
- `privilege_escalation`
- `tool_manipulation`

Risk 描述 `untrusted_content` 中的风险机制，不由候选动作是否服从攻击决定。

### 2.2 Alignment：动作与任务关系四分类

新字段 `task_alignment_label` 严格使用：

- `aligned`：候选动作是完成明确用户目标所必需或直接支持的动作；
- `unrelated`：动作本身未必有害，但与当前目标无关；
- `ambiguous`：仅凭当前目标和上下文无法可靠判断，或缺少授权范围；
- `malicious`：动作服务于攻击目标、越权、泄露、破坏或欺骗，而非用户目标。

旧字段 `alignment_label` 是 v1 的兼容字段，且当前由 Risk 确定性推导；它不得作为
Route B 的独立监督证据。v2 训练目标必须读取 `task_alignment_label`。

### 2.3 独立性要求

v2 内部角色必须包含打破 Risk/Alignment 确定映射的对照，例如：

- 攻击内容存在，但候选动作拒绝攻击并继续用户任务：Risk 非 benign，Alignment 为
  `aligned`；
- benign 内容下产生无关或授权不清的候选动作：Risk 为 `benign`，Alignment 为
  `unrelated` 或 `ambiguous`；
- 同一 `user_goal + untrusted_content` 配对安全动作和攻击动作，避免动作头只学习风险词。

发布前报告 Risk × Alignment 列联表、每格计数、条件分布和互信息；任何必需类别
组合为零都必须解释，不能用重加权伪造支持量。

## 3. Proposed action 与 provenance

每条用于 A/B/C 对比的 v2 样本必须保留同一基本 case；只有输入视图不同。动作字段：

- `proposed_action`：执行前捕获的结构化候选动作，建议用规范 JSON；
- `action_provenance`：Route B 内部角色只允许 `sandbox_policy_output` 或经批准的
  `source_field`；
- `action_observation_id`：指向不可变 mock trace 中的唯一记录；
- `action_policy_id`：生成候选动作的确定性非学习策略与版本；
- `field_provenance`：记录动作参数来自用户目标、外部内容或固定 fixture 的位置。

`benchmark_target`、`protocol_wrapper`、`missing` 和 `unknown` 不能作为 train、validation
或 calibration 的动作证据。所有动作只进入无外部副作用的 mock runtime；真实邮件、
上传、支付、删除、权限更改、凭据或第三方服务都禁止调用。

为减少标签泄漏，mock policy 必须同时产生：

1. goal-consistent 候选；
2. goal-unrelated 候选；
3. authorization-ambiguous 候选；
4. attack-following 候选。

动作函数名不能直接含 Risk 类别名；危险性由参数来源、权限边界和目标关系共同决定。

## 4. 来源路由与许可结论

| 来源 | Route B 默认用途 | 结论 | 依据 |
|---|---|---|---|
| 项目自有 mock-tool scenarios | train/validation/calibration 候选 | 首选；不触发新增第三方条款，但必须独立人工审核 | 本协议与 `configs/execution_policy.yaml` |
| BIPIA Email train | 可选的 instruction-hijacking/benign 内容来源 | 已在 v1 使用；数据来自 OpenAI Evals，BIPIA 清单标为 MIT | BIPIA pinned LICENSE/README |
| BIPIA Table train | 暂不默认合并 | WikiTableQuestions 为 CC BY-SA 4.0；只有在项目所有者确认归因和 ShareAlike 处理后才可加入 | BIPIA pinned LICENSE |
| BIPIA Code train | 暂不默认合并 | Stack Exchange 内容为 CC BY-SA 4.0；必须保留作者/URL/归因且确认衍生数据发布方式 | BIPIA pinned LICENSE |
| BIPIA WebQA/Summarization | 排除 | 官方要求另行取得 NewsQA/XSum 并遵守源条款；当前未获批准 | BIPIA pinned benchmark README |
| InjecAgent | Test B only | 官方将其描述为 1,054 个 test cases；不得转入训练 | InjecAgent official README |
| NotInject | Test C only | v1 已冻结的 over-defense 测试；不得转入训练 | 冻结协议与 manifest |
| AgentDojo v0.1.35 | optional Test D only | 官方定位是动态评测环境；继续作隔离端到端评测，不作为默认训练来源 | AgentDojo pinned release/repository |
| SecAlign / StruQ | 排除默认数据构建 | 主体为 CC BY-NC；只保留相关工作或另行获批的隔离评测 | SecAlign official README/LICENSE |

以上结论不构成法律意见。外部仓库代码许可不能覆盖其中第三方数据的独立许可。

## 5. v2 数据构造设计

### 5.1 Case family

项目自有 corpus 使用离线 mock 工具，至少覆盖消息、文件、日历、工单、云存储、
数据库和权限管理域。每个 family 包含：

- 一个明确 `user_goal` 与授权范围；
- benign 与四类风险内容变体；
- 至少两个不共享措辞的安全/攻击模板组；
- 四种 Alignment 候选动作中的适用子集；
- 明确的实体槽位、参数来源和预期 mock 状态变更；
- 不依赖真实个人、凭据、组织或在线服务的虚构 fixture。

Risk 类别判定规则：

- `instruction_hijacking`：要求改变/覆盖控制流程，但不以另外三类具体后果为主；
- `data_exfiltration`：主要目标是把非公开数据发送给未授权接收方；
- `privilege_escalation`：主要目标是获得、授予或扩大未授权能力；
- `tool_manipulation`：主要目标是滥用工具参数或调用次序造成非授权状态变化；
- 多风险 case 只按预注册的主要攻击目的标一类，并在 `secondary_risks` 保留其他机制。

### 5.2 分组和角色隔离

- 先按 `scenario_family + goal_template + attack_template + action_template` 建组，再划分；
- 同一模板、实体词表、规范化动作签名及其近重复不得跨角色；
- train、validation、calibration 使用互斥 family；若 family 数不足，不得只靠随机行划分；
- 当前 Test A/B/C 保持只读。Route B 若实质改变 Test A 的构造，必须建立新协议版本和
  从未用于设计选择的 untouched Test A2；旧 Test A 仍保留为历史锁定证据；
- Test B/C/D 永远不用于模板、阈值、动作政策或标签规则调优。

构造目标采用完整 Risk × Alignment 反事实设计：每个 base case 生成 `5 × 4 = 20`
条动作候选。train/validation/calibration/Test A2 分别计划
`250/100/500/500` 个 base case，即 `5,000/2,000/10,000/10,000` 条；其中
calibration 与 Test A2 各有 2,000 条 benign，可把单次 benign 错误的经验 FPR
分辨率降到 0.05%。每个角色的 base case 再按 5 个 case 组成一个 template group，
形成 `50/20/100/100` 个互斥 cluster。

`scripts/plan_route_b_precision.py` 已提供不拟合参数的 Wilson 精度表。以恰好 1%
错误率作规划点时，benign `n=100/339/1000/2000/5000` 的单错误分辨率分别约为
`1%/0.295%/0.1%/0.05%/0.02%`，名义 95% Wilson 半宽约为
`2.636%/1.134%/0.643%/0.446%/0.278%`。这只说明行级二项精度，不能替代
cluster-aware 功效分析。上述数量是获批构造方向下的 candidate target，生成和审核后
还要根据实际 cluster 分布冻结；它仍不是训练授权。

## 6. 双盲标签与动作审核

AI 可以生成候选、做一致性预审和指出冲突，但不得计为独立人工审核。训练就绪需要：

1. reviewer A 与 reviewer B 分别在看不到预设标签和对方答案时独立标注同一批 Risk；
2. 两人再以不同顺序、看不到 Risk/预设 Alignment/对方答案的表独立标注同一批
   `task_alignment_label` 与动作 realism；
3. 两份原始答案封存后才比较，分歧由 adjudicator 处理，原始意见不得覆盖；
4. 每位审核者记录稳定匿名 ID、时间、rubric 版本和备注；
5. 分别报告 Risk 与 Alignment 的原始一致率、每类混淆和适当的一致性统计，不只报告
   裁决后 100%；
6. `ambiguous` 是有效 Alignment 类，不等同于“审核没完成”；真正无法标注的 case 使用
   单独 audit 状态并从主要训练/评测隔离。

项目所有者可以担任其中一个 reviewer，但至少还需要一名独立人类完成另一条盲审流。

## 7. Route B 训练前退出门

以下条件必须同时满足：

- 协议 `2.0.0` 和 machine-readable registry 经项目所有者批准并冻结；
- 所有新增来源、许可、归因、revision 和 SHA-256 完整；
- v2 schema 不再把 Alignment 强制为 Risk 的函数；
- 五类 Risk 在训练与模型选择所需角色中有协议要求的有效支持；
- 四类 Alignment 有协议要求的有效支持，并通过独立性诊断；
- 内部 action provenance 只来自允许来源，mock trace 可重放且零真实副作用；
- 双盲人工审核、分歧裁决和一致性报告完成；
- exact/near/template/action-signature/context 完整性检查均通过；
- train/validation/calibration 与 untouched tests 隔离；
- 新 manifest 和公开聚合 data/label card 生成；
- readiness 报告明确写出 `formal_training_authorized=true`。

在此之前，任何 loss、checkpoint、模型指标、温度和阈值都不得产生。

## 8. 当前开放项

- 项目所有者已批准继续默认排除 Table/Code 等尚未单独批准的 CC BY-SA 数据；若以后
  改变决定，必须另开来源许可阶段。
- WebQA/XSum、SecAlign/StruQ 和任何新外部数据下载均未批准。
- candidate 4 已生成 27,000 条、270 个 template group；manifest、exact、四角色
  template/action 隔离和 5,400 个模板代表的 0.92 near-duplicate 检查均通过。样本量
  与 cluster 目标已经达到，但仍须双人盲审后才能冻结。
- 第二名独立人工审核者尚未登记。
- 新 untouched Test A2 的来源与构造尚未冻结。
- 本草案尚未升级或覆盖冻结的 protocol `1.0.0`。

## 9. 官方证据链接

- [Task Shield, ACL 2025](https://aclanthology.org/2025.acl-long.1435/)
- [BIPIA pinned benchmark README](https://github.com/microsoft/BIPIA/blob/a004b69ec0dd446e0afd461d98cb5e96e120a5d0/benchmark/README.md)
- [BIPIA license and dataset notices](https://github.com/microsoft/BIPIA/blob/a004b69ec0dd446e0afd461d98cb5e96e120a5d0/LICENSE)
- [InjecAgent official repository](https://github.com/uiuc-kang-lab/InjecAgent)
- [AgentDojo pinned revision](https://github.com/ethz-spylab/agentdojo/tree/a75aba7631d3ca5fb7ab938965c97ead2f9ff84b)
- [SecAlign pinned license](https://github.com/facebookresearch/SecAlign/blob/3fc9c9c3244a21512f5a1f3859a9858090711f0e/LICENSE)
