# Candidate 9 动作来源核验

日期：2026-09-09。范围：为五类 Risk、四类 Alignment 与动作证据补齐寻找公开训练素材；本次仅查询论文、数据卡和文件元数据，未下载以下数据文件或执行模型。

后续更新：项目所有者已明确回复“批准下载并只读审计”。批准范围记录于 `configs/candidate_9_toolsafety_audit.yaml`，ToolSafety 固定文件正在下载；下文未下载描述是来源核验时的状态。批准不等于训练候选接入许可。实际下载成功与哈希以 `data/raw/toolsafety/source_manifest.json` 为准。

2026-09-10 更新：下载已完成并通过固定 SHA-256 核验，只读结构审计已完成，实际快照 15569 条；详情见 `reports/data/toolsafety_readonly_audit_20260910.md`。以下来源核验时状态保留为历史记录。

## 检索记录

使用 nature-academic-search 的 multi-source-search 流程。学术 MCP 未挂载；Conda Python 以 UTF-8 运行备用 OpenAlex 查询 `agent tool use trajectories instruction tuning` 成功，但宽泛结果未提供直接可接入数据。随后用官方论文、作者主页及官方数据卡核实搜索发现，按论文 DOI/arXiv ID 合并同一工作的重复条目。下表不是穷尽性系统综述。

| 来源 | 核验结果 | 当前决定 |
|---|---|---|
| AgentTuning / AgentInstruct | ACL Findings 2024，DOI `10.18653/v1/2024.findings-acl.181`。官方卡提供 1866 条六任务轨迹；任务名称充当 split 名称，不是 train/validation/test 划分。HF revision `e252cf78ced8a0ea5f62cfd591784cdbbddbac8a` 未提供明确 license 字段或 LICENSE 文件 | 暂不下载；不能用第三方汇总页标注的 Apache-2.0 替代原始发布条款 |
| AgentDoG 1.0 Training Data | 预印本 `2601.18491`。HF revision `f4da9da000e1bde5dce851e522bcb1e3c50684ed`，两个 train 配置分别为二元安全与细粒度分类；卡片各称 4000 条，不能相加声称 8000 个独立轨迹 | 标签和动作内容相关，但卡片 license=other，明确要求就 derivative-use 等条款咨询维护者；暂不下载、不进行派生转换。代码仓库 Apache-2.0 不自动覆盖此数据 |
| ToolSafety | EMNLP 2025，DOI `10.18653/v1/2025.emnlp-main.714`。论文和作者主页均指向 `jinjinyien/ToolSafety`，卡片 MIT；固定 revision `7c444473e0dc0a822247858c249b10856ade04ef`。论文包含多步模拟轨迹及提示注入子集 | 优先提出本地下载与可用性审计；尚未批准、下载或纳入候选。需核对上游工具来源、实际字段和本项目标签适配 |

## ToolSafety 的具体审计范围

- 固定文件：`toolsafety.json`，223041316 bytes（约 223 MB），HF LFS SHA-256 `e623a0e72b2faf5270876462dc8a3197967c533b00755a80050187db34bcbd72`；README 138 bytes。上述来自固定 revision 的官方文件树元数据，尚未本地核验文件内容。
- 官方卡声明 MIT；保留作者、论文、来源、许可证元数据与下载哈希。作者主页的代码链接返回 404，但数据链接可访问且与论文一致。
- 下载后先做只读审计：实际记录数、对话角色、工具定义/调用/返回可配对性、模拟轨迹属性、模板及重复结构。没有源动作的样本不填造动作，不把拒绝回答当工具调用。
- 论文报告 5668 个直接危害、4311 个间接危害、4311 个多步样本，含 224 个提示注入样本；这些是论文统计，不能提前认定下载快照计数或最终可用规模相同。
- 工具描述来自 Glaive Function Calling V2、ToolBench、ToolAlpaca。逐来源条款和归属仍需追踪，MIT 数据卡不作为覆盖所有上游权利的证明；未厘清前不进入训练候选或发布派生内容。
- 它主要训练安全回应，含模拟轨迹；不能称为真实外部执行日志。直接有害用户请求不自动符合本项目间接提示注入任务；间接有害输出也不自动属于五类 Risk 中的攻击。只在样本语义和信任边界明确时提出标签映射，仍需独立审核。
- 论文采用其训练数据和另列外部评测；没有找到可照搬的内部 train/validation/calibration 比例。后续若接入，先按原始轨迹、工具及场景家族分组，排除已锁定集合重叠，再采用项目派生划分；不得称为官方 validation/test。

## 一手证据

- [AgentTuning ACL 论文](https://aclanthology.org/2024.findings-acl.181/)；[AgentInstruct 固定数据卡](https://huggingface.co/datasets/zai-org/AgentInstruct/blob/e252cf78ced8a0ea5f62cfd591784cdbbddbac8a/README.md)。
- [AgentDoG 固定数据卡](https://huggingface.co/datasets/AI45Research/AgentDoG1.0-Training-Data/blob/f4da9da000e1bde5dce851e522bcb1e3c50684ed/README.md)；[官方代码 README](https://github.com/AI45Lab/AgentDoG)。
- [ToolSafety 论文](https://aclanthology.org/2025.emnlp-main.714/)；[论文 PDF](https://aclanthology.org/2025.emnlp-main.714.pdf)；[作者主页中的数据链接](https://tarfersoul.github.io/)；[固定数据卡](https://huggingface.co/datasets/jinjinyien/ToolSafety/blob/7c444473e0dc0a822247858c249b10856ade04ef/README.md)；[固定文件树](https://huggingface.co/api/datasets/jinjinyien/ToolSafety/tree/7c444473e0dc0a822247858c249b10856ade04ef?recursive=true)。

本报告完成候选入口核验，不证明新的五类风险或动作训练集已形成。下一步下载审计需要项目所有者批准新来源和该文件规模，依据 `configs/execution_policy.yaml`。

补充条款线索：官方 GitHub license API 将 [ToolAlpaca LICENSE](https://github.com/tangqiaoyu/ToolAlpaca/blob/main/LICENSE) 和 [ToolBench LICENSE](https://github.com/OpenBMB/ToolBench/blob/master/LICENSE) 识别为 Apache-2.0，[Glaive Function Calling V2 数据卡](https://huggingface.co/datasets/glaiveai/glaive-function-calling-v2/blob/main/README.md) 也声明 Apache-2.0。这是仓库/数据卡级别的证据；尚未核对 ToolSafety 逐样本的上游工具映射及第三方 API 文档归属，不能将其报告为完整权利链审计通过。
