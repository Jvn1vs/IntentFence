# AIB Alignment审核材料包

2026-09-12。为已有23条观测生成两套待填写表，未执行审核，不宣称盲审或独立性成立。

通过白名单仅呈现最新user_goal、动作前history（含system）、原source_tool_definitions和proposed_action。排除外层ground_truth、源案例ID、策略名、家族、字段选择线索和旧AI意见。保留材料本身的攻击内容，不能通过删攻击实现“去答案”。两套表使用不同稳定顺序，opaque review_id映射另存coordinator_only。

待填review_status、Alignment、动作形式、notes、reviewer_id、reviewed_at均为空。逐行CSV往返解析与material_sha256比较通过，A/B均23项。表内同源内容可能自然暴露关联，不保证无法猜测案例；材料整理不等于独立执行隔离。

ignored目录 `data/interim/aib_alignment_review_20260912`：

- reviewer_A/alignment.csv SHA-256 `5d4f967e2b95a44bc9fcb5721956073798748e65ea48b6135337125951d2f2ba`。
- reviewer_B/alignment.csv SHA-256 `91fcfb905954ab850a92a9df2ac17d7dded4ed0e8bb596291b7fa978e2f0dd7a`。
- coordinator_only保存mapping和manifest，不提供给审核者。

审核规则见 `docs/aib_alignment_review_instructions_20260912.md`。本包是Alignment专项，不替代独立Risk审核或完整协议验收。真正审核仍需符合冻结协议的两种不同provider/model/revision执行身份与盲态；当前root已看过答案，不能充任独立审核者。

新增打包脚本及2项fixture测试，2 passed（0.54秒）、相关Ruff通过；覆盖白名单排除未来/种子标签、CSV多行文本及空审核字段。Conda命令 `python -m scripts.package_aib_alignment_review`，输出目录存在时拒绝覆盖。

下一步实现回收文件的不可变列、身份与弃权合法性检查，并核实可用的独立审核执行条件。当前23条仍未训练就绪，unrelated/ambiguous及来源隔离缺口没有因打包消失。
