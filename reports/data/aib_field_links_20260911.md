# 23条AIB观测字段来源与上下文核验

2026-09-11。固定适配寄存文件、六批原观测、AIB原始数据和家族约束哈希，重建每条动作前prefix并解析字段引用。没有改写原数据、分配split或赋标签。

## 结果及准确范围

- 20条：所有动作参数与来源span逐字相等。
- 2条航班观测：JSON指针定位carrier/price/stops，确定性文本与这些字段对应；这不证明“最低价”陈述真假，不能把字段正确误报成任务对齐正确。
- 1条澄清：联系人引用可定位，原问题码保留；字段解析本身不证明正文确实缺失或澄清充分。
- 14个按source case和原前缀哈希绑定的上下文组，其中9组各两条观测。已有prefix_sha256与重建值匹配；没有原prefix_sha256的记录以原文件boundary重建，保留这种证据来源差异。
- 每项关联完整must-link成员。上下文组不是已经审核的action_pair_group，后者仍null；尚未验收同Risk/role及不同Alignment标签条件。

对span检查非负消息索引和完整边界，拒绝布尔索引；存在角色声明则比较来源角色，存在授权span则必须指向最新user。适配原观测与原文件按位置取出的观测进行完整比较。未读取动作后消息用于参数解析，未读取模型预测。

## 实现与验证

新增 `scripts/verify_aib_field_links.py` 与4项fixture测试：参数错配和越界/非法索引失败，相关4 passed（0.53秒）、Ruff通过。真实固定23条均完成上述限定范围核验。仍需要更完整的行为覆盖测试及最终集成验收，不能以4项fixture宣称整个Route B通过。

ignored `data/interim/aib_field_links_20260911/report.json` SHA-256 `727fcc86c3136c102a3a164db8b2af68d68725b56e954e90a731d05a8c8f9ea2`，保存逐观测字段检查类型、前缀哈希、上下文组、家族成员和输入哈希。Conda命令 `python -m scripts.verify_aib_field_links`，拒绝覆盖。

下一步在这些来源链接上组织可供独立审核的材料，去掉策略名和既有意见以避免答案泄漏；审核者独立性和授权仍需如实满足。继续保留缺失unrelated/ambiguous类别、来源隔离和配对验收缺口，不用结构核验替代数据目标。
