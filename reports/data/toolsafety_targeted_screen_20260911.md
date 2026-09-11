# 三条 ToolSafety 动作候选的保护文本筛查

2026-09-11，按持续数据审计授权执行；不改变准入状态。

固定上一阶段三条复查记录和200条前缀文件的SHA-256；复用AIB审计登记的13个保护文件并逐一验证当前字节哈希。读取54,483项 user_goal/untrusted_content/context 或BIPIA测试攻击文本，不读取模型预测或评价结果。

查询只含所选前缀的user/tool消息，另递归提取工具JSON的字符串值，避免包装结构掩盖原文重叠；不读取动作后的消息。使用现有 SimilarityIndex 的规范化精确匹配和5-shingle Jaccard ≥0.8规则。

| review_id | 去重查询数 | 命中查询数 |
|---|---:|---:|
| ts-5179-4-7f8ff98be7af | 14 | 0 |
| ts-7441-2-6510aadcfe7f | 10 | 0 |
| ts-8020-2-697b69e99049 | 7 | 0 |

这不是完整泄漏排除：未比较系统工具定义、动作/工具家族、语义改写或完整AgentDojo来源，其他197条也不在本次查询范围。三条仍保持training_ready=false，没有应用标签。

## 上游归属调查

针对 random_word_api、sentiment_on_markets、sport_sante 的三项官方仓库限定搜索均未返回结果；这不能证明工具不存在。直接读取[ToolBench官方说明](https://github.com/OpenBMB/ToolBench#data-release)，确认工具JSON/API代码位于单独发布数据的toolenv目录，源工具映射应继续从该目录查证。官方说明声明数据Apache-2.0，仍不证明这三条ToolSafety记录与具体工具条目、版本及第三方描述的对应。此次没有下载完整ToolBench数据包，没有获得新的准入结论。

## 复现与验证

Conda intentfence下执行 `python scripts/screen_toolsafety_targeted.py`。脚本拒绝覆盖已有报告，源快照或保护文件哈希不符会失败。新增两项fixture测试验证嵌套文本提取、排除assistant和动作后字段；2 passed（0.31秒），相关Ruff通过。首次执行后修正Ruff要求，保留screen.json历史记录，当前实现产物为screen_v2.json。

ignored `data/interim/toolsafety_targeted_screen_20260911/screen_v2.json` SHA-256：`fe937af6cd926c941bfd8b6ca6c7dd9aece5a56f25282bf5799caa3c1eae431f`。内含全部输入及实施脚本哈希。

下一步优先查找官方toolenv小范围元数据/条目，建立三种工具的可验证对应；找不到则保持来源隔离，不以零文本命中代替条款与家族隔离。未启动训练、调用源工具或改动第一轮模型证据。
