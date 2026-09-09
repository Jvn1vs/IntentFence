# Candidate 9 多任务数据补齐决定

日期：2026-09-09。项目所有者明确回复：“继续补齐原五类风险和动作数据”。阶段状态以 `docs/task_progress_plan.md` 为准。

## 固定目标与当前缺口

保留 candidate 8 第一轮工程结果，继续五类 Risk 与四类 Task Alignment 的动作感知目标。candidate 9 v3 的 20691 条是背景与攻击配对数量，不代表新增同等数量的独立场景，也不代表多任务数据已经就绪。

2026-09-09 对本地 train/validation 的只读字段统计：train 14582 条中，暂定 benign=3653、instruction_hijacking=10929；validation 2065 条中分别为 517、1548。两角色共 16647 条全部缺少 `task_alignment_label`、`proposed_action` 和 `action_pair_group`，`human_verified=true` 为 0 条。本检查未读取校准/测试内容来设计新样本，计数不代表标签正确性审核。

| 目标 | 当前证据 | 下一步需要补齐的证据 |
|---|---|---|
| benign | 公开正常背景，尚为暂定标签 | 逐条语境核对及自然安全讨论等困难负样本审核 |
| instruction_hijacking | BIPIA 家族插入，尚为暂定标签 | 逐条攻击意图复核，区分其他风险类别；增加不同表达及载体 |
| data_exfiltration | v3 无此类已审核标签 | 有敏感资源、未授权目的地和任务授权边界的独立场景 |
| privilege_escalation | v3 无此类已审核标签 | 有原始权限、越权请求和工具能力边界的独立场景 |
| tool_manipulation | v3 无此类已审核标签 | 有工具名称、参数及预期用途的操纵场景，记录与其他类的边界 |
| aligned / unrelated / ambiguous / malicious | v3 均未标注 | 根据用户目标与拟执行动作分别审核；不得由 Risk 自动映射 |
| 拟执行动作 | v3 缺失 | 来源中的实际动作字段，或可重放离线沙箱策略观测 |

## 数据实现约束

1. 先审查已有 train/validation 素材与适配接口；禁止通过读取最终测试预测或错误来设计新训练场景。既有 calibration 和测试继续锁定。
2. 新公开来源先核实官方论文/文档、固定版本、许可证、原始划分及与锁定集合重叠。未通过条款或隔离检查的来源不进入训练候选。InjecAgent 仍为 Test B，不能改作训练。
3. 对缺少动作的公开文本，不将 Dolly response、攻击者期望结果或人工拼接包装冒充实际动作。沿用协议允许的 `source_field` 或 `sandbox_policy_output`；后者必须有 `action_observation_id`、`action_policy_id` 和字段来源，且只运行离线 mock。
4. 公开自然内容、项目自建场景和沙箱派生观测分别保留来源及证据类型。自建部分避免单一统一模板，记录场景、目标、攻击、动作家族与规范化动作签名，防止同族跨角色。
5. Risk 与 Alignment 分开审核。暂定标签允许被纠正；AI 预审如实记录为 AI，保持 `human_verified=false`，不替代协议中的独立人审。
6. 不直接覆盖 v3，也不通过修改既有实现或 manifest 改写历史证据。后续候选使用新目录及版本化配置，并重新检查分组隔离、标签覆盖、动作可重放性和许可证归属。

## 下一阶段交付与退出条件

现有 `src/intentfence/route_b.py` 还要求 `action_pair_group`：同一目标、内容、Risk 和角色下，需要至少两种不同 Alignment 的不同动作。必须保留“有攻击内容但动作仍 aligned”与“正常内容但动作 unrelated/ambiguous”的反例，避免两个任务相互泄露标签；每个内部角色都须覆盖五类 Risk 和四类 Alignment。

现有 `src/intentfence/mock_runtime.py` 只对给定工具与参数作离线规范化记录，返回 `executed=false`；哈希可验证记录一致性，但不能证明真实代理自主产生过该动作。后续还须保存输入、策略实现及其选择动作的过程，明确这些是沙箱派生观测，不冒称真实工具执行轨迹。

- 逐来源、逐类别覆盖清单，明确哪些字段来自原数据、哪些来自沙箱、哪些缺失。
- 新来源可用性核验或明确排除理由；涉及新条款时先形成具体可审批范围。
- 动作证据适配方案及 fixture 验证，覆盖缺失动作、伪造来源、不可重放记录和 Risk/Alignment 被错误绑定等失败情况。
- 确定候选构造规则后再生成新版数据；未通过上述检查前不声明训练就绪，不承诺模型收益。

当前决定只授权继续数据与实验准备。模型参数更新、训练、校准和正式最终测试评测仍遵守仓库执行边界。
