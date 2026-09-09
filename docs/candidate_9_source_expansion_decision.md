# Candidate 9 后续公开来源的具体选择

调查日期：2026-09-08。更新：2026-09-09 已记录项目所有者明确回复“批准按上述范围使用 Dolly-15k”；固定版本数据文件和 README 已下载并记录 SHA-256。下文“建议批准”保留为本次批准的范围依据。

## 为什么需要补充来源

candidate_9_v2 的 3620 条样本完整性通过，但训练中 2536/2550 条为 Table 衍生，不能认为已解决模板/场景单一问题。原先选择的 InjecAgent 原子素材全部与其测试指令重叠，不能通过重新组合充当独立训练来源。

## 已核验的替代候选

| 来源 | 一手证据 | 决定 |
|---|---|---|
| deepset/prompt-injections | 固定 revision `4f61ecb038e9c3fb77e21034b22511b523772cdd` 的 README 顶层 license=apache-2.0，但 dataset_info.license=cc-by-4.0；官方 train/test=546/116 | 暂不下载，不能只摘取页面顶层许可证标签 |
| xTRam1/safe-guard-prompt-injection | 固定 revision `a3a877d608f37b7d20d9945671902df895ecdb46` 的卡片没有明确 license；卡片计数为 8236/2060，文字叙述采用另一组规模 | 暂不纳入，许可证与划分说明需要厘清 |
| PIGuard 训练集合 | 官方 README 说明训练汇集 20 个来源和 LLM 增强；其 validation 使用 NotInject/BIPIA/WildGuard/PINT | 不照搬其 validation 方案；已有测试锁不允许这样调参，聚合训练数据须逐源追踪条款 |
| Databricks Dolly-15k | 官方数据卡明确 CC-BY-SA-3.0，说明人工编写、带 Wikipedia 参考文本的任务，支持数据增强；文件树给出 JSONL 大小 13,085,339 bytes | 推荐作为正常背景来源，待所有者批准新条款 |

一手来源：

- [deepset 固定版本原始数据卡](https://huggingface.co/datasets/deepset/prompt-injections/blob/4f61ecb038e9c3fb77e21034b22511b523772cdd/README.md)。
- [SafeGuard 固定版本原始数据卡](https://huggingface.co/datasets/xTRam1/safe-guard-prompt-injection/blob/a3a877d608f37b7d20d9945671902df895ecdb46/README.md)。
- [PIGuard 官方仓库](https://github.com/leolee99/PIGuard)；[ACL 2025 论文](https://aclanthology.org/2025.acl-long.1468/)，DOI `10.18653/v1/2025.acl-long.1468`。
- [Dolly 固定版本数据卡](https://huggingface.co/datasets/databricks/databricks-dolly-15k/blob/bdd27f4d94b9c1f951818a7da7fd7aeea5dbff1a/README.md)；[CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/)。

## 建议批准的具体范围

下载 `databricks/databricks-dolly-15k` revision `bdd27f4d94b9c1f951818a7da7fd7aeea5dbff1a` 的 `databricks-dolly-15k.jsonl`（约 13.1 MB），保存原数据卡、作者归属与哈希，只选择有非空 context 的 `closed_qa`、`information_extraction`、`summarization`。其余类别不伪造参考文本，不把 response 当作拟执行动作。

保持 CC-BY-SA-3.0 的来源/归属和适用条件，不将派生素材改标为项目 Apache-2.0。真实数据和派生数据留在本地忽略目录；本步骤不涉及发布数据、模型权重或启动训练。数据卡说明可作训练和增强，但普通指令数据没有安全标签，也没有 IntentFence 四类 Alignment 或动作真值；加入后仍需独立构造与标签审核。

划分将沿用 candidate 9 的背景/近重复成组隔离，先排除锁定测试/校准重叠，再安排四角色。Dolly 官方仅提供一个 train 集；我们构造的 holdout 必须标为 project-derived，不能冒称官方 test。尚未下载，所以不提前承诺筛选后行数、标签质量或增益。

## 已完成的准备与剩余条件

`src/intentfence/candidate9_sources.py` 已提供纯字段适配器；合成 fixture 覆盖三类任务、缺失背景拒绝、字段错误拒绝、source/revision/归属保留，不会产生安全/动作/人审声明。尚未连接真实构造入口，不会改变已封存 v2 的实现哈希。

新来源规则见 `configs/candidate_9_source_proposals.yaml`，owner_approved=true，批准证据已记录。确认要求来自当前 `configs/execution_policy.yaml` 的 `project_owner_executes: new_source_license_or_terms_approval`，而非检索 skill。此前“前两个来源”选择涵盖 BIPIA/InjecAgent；随后所有者另行明确批准了本方案的 Dolly 范围。proposal 中 downloaded=false 是下载前计划快照；实际下载事实与时间以 `data/raw/dolly/source_manifest.json` 为准，避免修改已绑定的批准文件哈希。

本次使用 nature-academic-search 的多来源流程。学术 MCP 未挂载；备用 OpenAlex 脚本初次发生 Windows GBK 输出错误，启用 UTF-8 后运行成功，但宽泛查询返回不相关论文，已排除。结论使用官方数据卡、仓库与 ACL 页面，未把搜索摘要或不相关高引论文当作许可证和可训练性依据。
