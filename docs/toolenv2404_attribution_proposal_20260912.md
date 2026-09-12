# ToolEnv2404小范围来源核查提案

目的：核查现有三条ToolSafety候选所用random_word_api、sentiment_on_markets、sport_sante工具定义。三条目前暂定unrelated1、ambiguous2，但上游对应未完成，不能直接纳入训练。已有AIB试点也未补齐四类Alignment。本提案不降低原五Risk四Alignment目标。

## 请求范围

仅下载官方stabletoolbench/ToolEnv2404固定revision `b6141cc50e0c72894517786e8c6b95b749270535` 的toolenv2404_filtered.tar.gz，11,706,795字节（约11.7MB），SHA-256 `8f5b0bccbf5cf64b937c7d1364536c2adc568cf069c523838702c7e62eec8302`，并保留已有官方数据卡及归属。2026-09-12已重新读取固定revision目录验证上述大小与LFS哈希，未下载档案。

[官方固定数据卡](https://huggingface.co/datasets/stabletoolbench/ToolEnv2404/blob/b6141cc50e0c72894517786e8c6b95b749270535/README.md)声明MIT。保留StableToolBench及条目内第三方API来源信息，不把MIT声明当成全部上游权利链已经闭合。只做本地只读来源审计，不作为新增训练来源授权。

档案作为数据读取：核对整体哈希，列目录、只读取匹配工具JSON，拒绝符号链接/非普通候选成员；不解压执行代码、不启动API服务器、不调用其中工具、不下载235.7MB Cache或任何模型。

## 可交付结果与失败出口

记录命中的成员路径/大小/哈希，比较工具名称、参数、描述与ToolSafety字段；明确完全一致、部分对应或未找到。即使找到同名工具，新抓取版本也未必就是ToolSafety生成时版本，不虚构谱系。未找到或归属不足时保留隔离结论，不追加档案下载。

下载量仅约11.7MB，但这是新的档案来源；`configs/execution_policy.yaml` 将new_source_license_or_terms_approval保留给所有者。持续自主推进授权覆盖常规阶段转换，不自动覆盖新来源条款。配置 `configs/toolenv2404_attribution_audit_20260912.yaml` 当前approval=false；收到明确来源批准后才下载。无需批准训练、发布或第三方工具调用，因为都不在本提案范围内。
