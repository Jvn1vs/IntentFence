# ToolSafety 三条多步候选的工具来源边界

## 论文能证明的生成过程

ToolSafety [官方论文 §3.2.1–3.2.2](https://aclanthology.org/2025.emnlp-main.714.pdf)说明：初始目标工具从 Glaive Function Calling V2、ToolBench、ToolAlpaca 收集；间接危害样本的工具结果由 GPT-4o 扮演的环境模拟器生成；多步轨迹再由 GPT-4o 根据原始良性问题、目标工具定义和少量示例合成，且最后一次调用必须是原单步样本的目标工具。论文没有提供每条前置辅助工具定义的来源索引，也没有证明轨迹中的工具曾真实执行。

这使三个前缀中额外工具的出现与论文方法**相容**，但不能由此断定具体六个定义一定由 GPT-4o 原创，或断定它们来自某个特定上游数据集。论文表1的 14,290 条与本地固定版本审计的 15,569 条也不同；论文中的总体统计不能替代这个版本的逐条核查。

## 本地可重放的三条证据

固定 ToolSafety 源 revision 为 `7c444473e0dc0a822247858c249b10856ade04ef`；动作前缀清单 `data/interim/toolsafety_prefix_review_20260911/prefixes.jsonl` 的 SHA-256 为 `bb978876abb0ced7c2c8dafd51c6fc1902eb542a2296a25ada07fd4410e3121f`。固定 ToolEnv2404 档案及三份匹配 JSON 的哈希见 `reports/data/toolenv2404_attribution_audit_20260915.md`；比较输出 `data/interim/toolenv2404_audit_20260912/comparison_20260915.json` 的 SHA-256 为 `7f6e69057e92e7a7b433193ed845c99594641cb6262bd0ff9136d4221398a027`。

| 前缀 | 目标调用的来源对应 | 前置辅助定义的现有证据 | 当前动作判断 |
|---|---|---|---|
| `ts-5179-4-7f8ff98be7af` | `article_summary_for_sentiment_on_markets` 的定义匹配 ToolEnv 的 `Finance/sentiment_on_markets.json` | `find_latest_article_by_topic`、`analyze_sentiment_of_text` 不在该匹配 JSON；具体来源未证实 | 文章 `id=1041425` 来自默认值，无法与此前选中的文章建立对应；Alignment 暂定 ambiguous |
| `ts-7441-2-6510aadcfe7f` | `get_individual_news_source_news_for_sport_sante` 的定义匹配 `Sports/sport_sante.json` | `find_relevant_news_source`、`summarize_news_articles` 不在该匹配 JSON；具体来源未证实 | 前缀选中 ESPN，调用使用 `newspaperId=vidal` 默认值；缺少 ID 映射，Alignment 暂定 ambiguous |
| `ts-8020-2-697b69e99049` | `get_french_word_for_random_word_api` 的定义匹配 `Data/random_word_api.json` | `generate_random_english_word`、`get_phonetic_pronunciation` 不在该匹配 JSON；具体来源未证实 | 用户要翻译已选的 `eloquent`；目标函数无源词参数、只生成随机法语词，Alignment 暂定 unrelated |

ToolEnv 仅是固定版本的字段对应证据，并非 ToolSafety 原始制作时使用了该版本的证明；三份匹配 JSON 的 MIT 数据卡也不能自动替代第三方 API 商户的权利核验。辅助定义的“未在匹配 JSON”只限定于三份对应文件，不能外推为整个 ToolEnv 档案或其他上游均不存在。

## 候选处理

三条源动作维持隔离，`training_ready=false`，不应用正式 Risk/Alignment 标签或 split。`ts-5179` 和 `ts-7441` 缺目标对象映射；`ts-8020` 有较明确的无关动作语义，但仍只是非盲 Codex/AI 复核。它们均不能充当四类 Alignment 的已审核训练样本，也不证明五类 Risk 的覆盖改善。

若未来需要把完整多步轨迹作为训练来源，应先获得六个辅助定义的逐条来源或明确将其归为论文合成轨迹、核验锁定集合与家族隔离、完成独立人审和同内容多动作对照。当前数据推进更应优先使用已有 AIB 隔离观测解决动作真实性与类别覆盖；不为这三条候选虚构缺失的来源或 ID 映射。
