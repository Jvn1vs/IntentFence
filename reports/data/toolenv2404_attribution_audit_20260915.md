# ToolEnv2404批准下载与三工具字段对应核查

2026-09-15，已记录所有者对11.7MB固定档案只读核查提案的“批准”。读取器准备阶段文档中的“待批”是历史状态，现由本阶段取代。授权仍不包含训练、发布或执行API。

## 下载与读取

固定revision `b6141cc50e0c72894517786e8c6b95b749270535`，档案11,706,795字节、SHA-256 `8f5b0bccbf5cf64b937c7d1364536c2adc568cf069c523838702c7e62eec8302`，与批准值一致。README 1,149字节，Git blob与批准的`162ac1ea7a9d344ffd92cac15083e89dc919f166`一致，SHA-256 `aa780039dfd5089aee3361b93ab4c53e54105af18e37ba1ed05634e8ab52099d`。保留MIT数据卡和原始归属信息。

原档案与source_manifest位于ignored `data/raw/toolenv2404/`。顺序读取12,354个成员，声明总大小168,209,687字节，只解析匹配JSON，未解压文件、运行代码或调用API。没有追加下载其他档案。

## 对应证据

| ToolEnv成员 | API定义数 | 与对应ToolSafety前缀的比较 |
|---|---:|---|
| Finance/sentiment_on_markets.json | 3 | 全部描述、必填参数、属性/默认值对应 |
| Sports/sport_sante.json | 2 | 全部对应 |
| Data/random_word_api.json | 9 | 8项规范化名称直接对应，1项显式双下划线别名对应；全部字段对应 |

比较仅将参数type大小写规范化；描述文本、参数名及默认值保持精确比较。第9项的ToolSafety名称为get_word_by_length__start_and_contain_for_random_word_api，不能把首次规范化名称未命中误记为工具不存在。显式别名核对单独保存，原名称不修改。

因此三个当前候选动作所用API定义均有匹配证据：按ID获取文章摘要、按newspaperId获取新闻、无参数随机法语词生成。随机法语词生成器不具源词翻译参数这一既有判断获得额外定义支持。文章ID/新闻来源ID与当前选择对象的对应仍未知，未调用外部API来猜测。

每个前缀另有两个未映射辅助工具：find_latest_article_by_topic/analyze_sentiment_of_text、find_relevant_news_source/summarize_news_articles、generate_random_english_word/get_phonetic_pronunciation。不能宣称这些工具已获逐条来源证明，也不能宣称相同字段就证明ToolSafety使用了这个抓取版本。API商户归属保存在匹配JSON，MIT声明不等于所有第三方描述的权利链已认证。

三条候选仍隔离、训练未就绪；下一步应核对ToolSafety的辅助工具生成方法及这六个定义的来源证据，明确可支持的轨迹来源声明，而不是继续要求用户重复批准本次已批准范围。

## 证据文件

- ignored `data/interim/toolenv2404_audit_20260912/metadata.json`：匹配成员、原JSON及字节哈希。
- comparison_20260915.json SHA-256 `7f6e69057e92e7a7b433193ed845c99594641cb6262bd0ff9136d4221398a027`。
- alias_check_20260915.json SHA-256 `30de5d86aad87058275020b770e2ccd9632354bf721e70d486689f70ba0af4ed`。

读取器4项fixture此前通过，批准前拒绝路径已验证；批准后真实档案读取与固定源哈希检查通过。中断前全量测试句柄已失效、终态输出不可取，不把它报告为通过，恢复后重新运行完整工程检查。

恢复后完整pytest：469 passed（95.84秒）；全仓Ruff、compileall通过。wheel在读取器准备阶段已成功构建，随后只修改批准配置和审计文档，未重复构建。
