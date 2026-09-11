# AIB五轮试点统一准备清单

2026-09-11。固定五轮记录、21条单次非盲AI意见、182条场景意见与保守家族约束，生成只读关联清单。没有合并训练集或赋标签。

## 当前实际覆盖

13场景、21观测（此前五轮统计为20操作提案及1澄清）。场景暂定Risk为：指令劫持2、工具操纵2、权限提升2、外传3、benign4。逐动作Alignment意见为aligned11、malicious7、弃权3，unrelated/ambiguous意见均没有；弃权不能计为ambiguous。

动作形式意见realistic18、unrealistic1、ambiguous2。筛选“同一案例至少两种不同、未弃权、realistic的Alignment意见”仅留下AIB-00026、00103、00167。此计数不是同前缀或独立标签验收，也不证明完整五风险动作对照覆盖。

## 按问题继续处理

| 记录 | 已知缺口 | 后续处理原则 |
|---|---|---|
| 00178:1 | 源SSH公钥不完整，动作形式unrealistic | 保留失败证据；不伪造公钥修补，另找完整源字段 |
| 00032:1 | 离线桶策略表示与实际接口语义未核实 | 核对mock schema是否准确表达源要求；不执行真实权限变更 |
| 00159:0 | 澄清使用内部missing_body代码 | 检查澄清的用户可理解性；不把澄清冒充完整操作或不同标签配对 |
| 00022:0、00099:0 | 部分文章摘录不能证明完成摘要任务 | 保留弃权，不为凑aligned改变用户原目标；寻找上下文完整的来源对照 |
| 00140:1 | 旧数值误用与四类Alignment的对应不确定 | 保留弃权，不把答案错误直接标成unrelated |

三条ToolSafety另行隔离，不混进此清单补四分类。统一清单为每条观测保留全部must-link成员，包括未被本次13场景选中的成员；不因筛选丢失跨案例家族关系。尚缺独立审核、完整家族隔离及split，所有正式标签/split仍null、training_ready=false。

## 文件与验证

- 新增 `scripts/build_aib_preparation_register.py`，复用逐动作核验器先验证五轮输入及动作哈希，再关联固定场景意见和家族文件。
- 新增 `tests/test_aib_preparation_register.py`：防止弃权/不合理动作补足对照，防止丢失未选中家族成员，缺失/重复成员失败。
- 相关9项fixture测试通过（4.35秒），相关Ruff通过。没有训练或使用正式测试模型结果。
- Conda复现命令：`python -m scripts.build_aib_preparation_register`；已有输出拒绝覆盖。
- ignored `data/interim/aib_preparation_register_20260911/register.json` SHA-256 `eead216c4935a2787fb33971cdd954006be8d5fe467eb3e6644224ff83ecacf5`。包含上游文件哈希与实施哈希；旧试点、旧清单与AI意见不覆盖。

下一步先核对已有桶策略和澄清表示的具体问题，再继续寻找上下文完整的指令劫持对照与来源明确的unrelated/ambiguous动作。保持原五风险、四Alignment和动作感知目标，不以现有21条作为训练就绪替代品。
