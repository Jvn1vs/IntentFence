# AIB 离线动作框架：首版实现与证据边界

用户确认上一阶段后，本阶段只实现框架并运行合成 fixture。未将 AIB 182 条场景接入策略，未生成真实来源动作、Alignment 或 split，也未训练。

## 已实现

`src/intentfence/offline_actions.py` 提供严格 Pydantic 输入、六种封闭的内存提案接口和四种确定性选择策略。配置为 `configs/aib_offline_actions_v1.yaml`，限定 `synthetic_fixtures_only`。这些是新的隔离接口，未改动 candidate 8 的 `mock_runtime.py` 或 Route B 构造入口。

| 操作 | 内存接口 | 参数 |
|---|---|---|
| lookup | memory.lookup | resource、query |
| return_result | memory.return_result | content |
| message | memory.message_proposal | recipient、body |
| file | memory.file_proposal | path、content |
| permission | memory.permission_proposal | resource、principal、access |
| update | memory.object_update_proposal | object、field、value |

上述接口只把有类型约束的字符串参数放入提案记录，不访问资源、不执行源调用。文件接口不读写目标路径，消息接口不发信，权限接口不改变权限。浏览器、shell、SQL、支付均未支持；不得把这类源动作强行映射为通用 update 来声称语义覆盖。

场景输入只接受动作前的完整 prefix，边界等于 prefix 长度。目标必须引用最新 user 消息。事实绑定 message/start/end 精确字符范围，分别标记 user、untrusted 或历史 assistant context。工具契约明确标为项目编写，不从受污染描述中恢复。授权需要用户来源证据与完整参数的明确许可；缺失许可不推定为允许。

goal_bounded 按目标引用解析参数并检查完整授权；unresolved_scope 使用同一保守规则，授权不足时返回澄清，授权完整时保留目标调用。它们不是两个独立学习策略。content_following 只解析低信任载体中精确 JSON 范围里的 operation 和参数事实引用，拒绝重复键、未知接口和缺失参数，不解释任意自然语言。stale_object 只从最新用户目标之前、同参数槽标记的历史事实中按事实 ID 排序取不同值；缺少这类证据时澄清，不造对象。

每份观测绑定完整输入、前缀、代码文件、配置及契约哈希，保留参数来源、目标/建议/授权引用、选择分支和内存前后摘要。内存变化仅为增加一条提案，资源不变。观测 ID 覆盖整份回执；没有源 Risk/Alignment、ground_truth 或 execution 的输入字段，也不自动赋训练标签。`executed`、`external_side_effects`、`human_verified` 和 `training_ready` 均为 false。

提供分组连边的角色一致性检查：任何连边跨角色都拒绝，因此给定图的连通分量不能跨角色。这不是家族发现器，也不证明调用方已经提供所有语义或派生关系；当前未实际建立 AIB 家族图或分配角色。

## 准备层仍需审核

操作种类、事实范围、语义参数槽、授权和可信边界仍由场景准备者提供。代码只验证结构与来源角色，不能凭字符范围证明人类自然语言已被正确理解，也不能识别被错误标成 prefix 的未来消息。后续真实来源转换必须核对原始行、原始决策边界和这些解释；本阶段没有提供原始 AIB 转换器。当前 fixture 的源哈希只是明确的合成占位，不作为真实源完整性证明。

`synthetic_fixtures_only` 是接口范围声明，不是能自动判断任意字符串来源的安全分类器。真实源接入仍遵循阶段授权与独立核验。也没有训练记录导出器或原始数据写入器；本阶段不会覆盖原始文件。

这些选择过程比仅记录预写动作更可重放，但仍是人工准备的结构化事实与固定规则驱动。不能称为真实代理自主轨迹、真实工具执行、独立 Alignment 审核或模型泛化证据。不能为补齐四类标签把四个策略名分别映射到四个 Alignment。

## 验证与下一步

测试位于 `tests/test_offline_actions.py`，覆盖六接口乘两类载体、同工具不同参数、未知/未授予授权、历史对象缺失、未来回复排除、标签拒绝、源字段与 schema 错误、重复 JSON 键、代码哈希绑定、嵌套输入重验证、跨角色连边和路径不覆盖。完整验证结果在进度计划中登记。

下一阶段建议先从已隔离的 AIB 场景中做少量真实来源适配试点：挑选现有接口能忠实表达、可信边界可还原的案例，保存原始行/前缀绑定及准备层解释，生成隔离观测并逐条检查动作合理性。不能预设每条都可用，不形成训练 split，不应用 Alignment 或启动训练。进入该阶段仍需所有者确认。
