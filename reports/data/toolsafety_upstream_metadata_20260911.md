# ToolSafety三条候选：官方工具元数据入口调查

2026-09-11。结论：发现进一步核查入口，但尚未建立逐工具对应，三条候选继续隔离。没有下载工具压缩包，没有新增训练数据来源。

## 已核查范围

- OpenBMB/ToolBench Git tree `d56fdd89faf8c91fa135090b212bb9057ee5cfc2`：238项，truncated=false。仓库包含data_example/toolenv示例，路径中没有random_word_api、sentiment_on_markets、sport_sante。此结论仅针对目录名，不能证明完整发布包缺失这些工具，也不是所有文件内容检索。
- [StableToolBench官方说明](https://github.com/THUNLP-MT/StableToolBench)直接链接ToolEnv2404及Cache，提供来源入口关系。没有将StableToolBench误记为ToolSafety的作者指定直接上游。
- [ToolEnv2404固定数据卡](https://huggingface.co/datasets/stabletoolbench/ToolEnv2404/blob/b6141cc50e0c72894517786e8c6b95b749270535/README.md)：MIT声明，描述新抓取工具集合。文件清单只有属性文件、README和11,706,795字节的toolenv2404_filtered.tar.gz；LFS SHA-256 `8f5b0bccbf5cf64b937c7d1364536c2adc568cf069c523838702c7e62eec8302`。新抓取版本即使存在同名工具，也不能直接证明ToolSafety生成时使用了这一版本。
- [Cache固定数据卡](https://huggingface.co/datasets/stabletoolbench/Cache/blob/c6aca0c1cda74d54915eccabb60984dc083fb14c/README.md)：仅说明是StableToolBench的cache/tools目录，无许可证声明。文件清单只有属性文件、README和235,732,308字节server_cache.zip；LFS SHA-256 `a3ed72052c2dc961d8e9b71860374d90ded6d475ca6f6449c78fb248cb82a5b2`。不以仓库许可证替代该包来源条款。

此次仅读取公共API目录、仓库信息和固定README，没有执行任何工具或下载档案。HF目录先从main读取，后登记当前revision；没有把目录读取宣称为固定revision内容核验，档案下载前仍须重新核对固定版本目录。

## 证据与后续处理

ignored `data/interim/toolsafety_upstream_metadata_20260911/receipt.json` SHA-256 `2802263955a8c261e280f8f1256f12cdc64be02f754211853013fd68d2b628e3`，登记各元数据文件哈希。ToolBench树响应SHA-256 `569592b5f56012264b423ab44560dcf26157715f9f1c4eccc86163bdd3982f0e`。

三条候选的上游归属仍unresolved；已有文本筛查不替代此条件。现阶段不扩大下载，先推进已有授权AIB试点的统一清单与缺口处理。若需利用这两个新来源的档案，则按execution_policy先形成具体范围、固定版本及来源条款提案；本次元数据发现不代表已获档案使用授权。

本阶段只调查并登记元数据，无行为代码变化，不重复测试。第一轮模型结果、既有split及标签保持原状态。
