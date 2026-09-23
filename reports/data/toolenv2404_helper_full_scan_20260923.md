# ToolEnv2404 六个辅助工具名全档案核查

已批准的固定 ToolEnv2404 档案 `data/raw/toolenv2404/toolenv2404_filtered.tar.gz` 为 11,706,795 bytes，SHA-256 `8f5b0bccbf5cf64b937c7d1364536c2adc568cf069c523838702c7e62eec8302`。既有对应审计只检查三份目标 API JSON，无法确定六个 ToolSafety 前置辅助定义是否在档案其他位置。本轮按同一只读授权，对全档案做有界字节检索，不解压到磁盘、不运行成员代码或调用 API。

## 结果

扫描覆盖 12,354 个成员中的 **12,304 个 JSON 文件**，声明未压缩总量 168,209,687 bytes。六个名称 `find_latest_article_by_topic`、`analyze_sentiment_of_text`、`find_relevant_news_source`、`summarize_news_articles`、`generate_random_english_word`、`get_phonetic_pronunciation` 在全部 JSON 成员内均无**区分大小写的精确 ASCII 字节匹配**。因此前份报告的“未在三份对应文件”可收紧为“未在这个固定 ToolEnv2404 档案的任一 JSON 成员找到这些精确名称”。

本结论只针对名称原文，不排除同义/改名定义、JSON 外内容、其他版本或其他上游来源；也不证明这些辅助工具一定由 ToolSafety 作者/生成模型原创。三个目标 API 定义的对应仍成立，但整段轨迹的六个前置定义归属仍未闭合，三条前缀继续隔离，`attribution_resolved=false`、`training_ready=false`、正式标签和 split 不变。

机器证据在 ignored `data/interim/toolenv2404_audit_20260912/helper_scan_v3_20260923.json`，SHA-256 `bb0863fc2411097030bd393d6a317ab8d85c8485df68c657b5eef54c501ea869`。`scripts/scan_toolenv2404_helpers.py --verify` 已从固定档案重放，并核对配置、读取器与脚本哈希。首次扫描漏掉一个名为 `.json` 的成员（12,303个 JSON），修正扩展名判断后扫描12,304个；保留前两版 ignored 输出以显示修正过程，最终只引用v3。四项夹具覆盖命中、隐藏 `.json`、路径逃逸/重名及大小上限。

下一步如要准入 ToolSafety 多步轨迹，仍需找到辅助定义生成/归属的逐条证据或明确可许可的生成链，并完成锁定集/家族隔离及独立语义审核。不能用本次零命中代替这些证据。
