# Candidate 9：三类缺失风险的动作来源核验

日期：2026-09-11。项目所有者已确认本阶段。目标仍为五类 Risk、四类 Alignment 和动作感知数据；本阶段只检索官方材料、核查代码与文件元数据，未下载新来源的数据文件或执行训练。

## 当前结论

没有确认一个能直接补齐全部缺口的现成训练集。优先提出 **AgentInjectionBench 的小规模只读审计**，验证其上下文、授权边界和动作来源；它只可能提供补充场景，不能替代多来源主体数据。批准范围另列于 `configs/candidate_9_aib_audit_proposal_20260911.yaml`，当前 `owner_approved=false`。

## 来源比较

| 来源 | 官方材料所支持的事实 | 对本项目的决定 |
|---|---|---|
| AgentInjectionBench | 作者 README 称发布 182 条手工场景（142 攻击、40 正常对照），有系统、工具、对话、攻击意图及执行约束。Apache-2.0。 | 优先只读审计；手工场景及预期约束不等同真实动作观测，不能把 unsafe 自动映射成 malicious Alignment。 |
| Agentic Prompt-Injection 5K | 固定卡片列实际合计 4935，官方 train/validation/test 为 3923/467/545；CC-BY-4.0。方法明确为模板填槽、确定性扩展与按模板隔离。schema 是文本分类字段。 | 不作为解决模板化或动作缺失问题的主来源；它的授权/工具攻击类别仍不能直接映射本项目风险标签。暂不下载。 |
| ASB | ICLR 2025 官方评测框架，支持观察注入等攻击。仓库 MIT；文件树有任务和攻击工具配置。 | 可作为场景/工具边界研究参考，尚未证明提供独立可用的训练动作日志；不能把攻击工具定义当代理实际动作。 |
| ToolSafe / TS-Bench | 论文有训练与评测划分，但当前公开仓库的可下载范围须与论文分别核验，详见下段。 | 不下载其 AgentDojo 等评测部分来补训练。 |
| AgentHarm | 官方数据卡请求只用于评测、不用于训练。 | 排除训练；派生来源也必须追踪这一上游限制。 |
| TraceSafe | 固定 HF 元数据声明 Apache-2.0，配置含注入、泄漏及接口异常；未取得足够训练用途、划分和动作来源证据。 | 保留线索，未通过训练入口核验。不能把一般参数错误算作 tool_manipulation 攻击。 |

一手链接：[AgentInjectionBench](https://huggingface.co/datasets/ppradyoth/AgentInjectionBench/blob/ef230359966c4d87b1c925aa56b8bf6e3f6ffed3/README.md)、[5K 固定卡片](https://huggingface.co/datasets/3nesdeniz/agentic-prompt-injection-5k/blob/e658d94dcafc133e3a4483f9f9aa13507f3848c4/README.md)、[ASB 官方仓库](https://github.com/agiresearch/ASB/tree/1f561dccf92d55302368fa67679b4ba9d9c8fdc4)、[AgentHarm 数据卡](https://huggingface.co/datasets/ai-safety-institute/AgentHarm/blob/main/README.md)、[TraceSafe 元数据](https://huggingface.co/api/datasets/CyCraftAI/TraceSafe/revision/b8d546242a7182d2f5a97f5ff88cecca63d8e719)。上述数量是发布者声明或元数据，不是本地逐条审计结果。

## ToolSafe 与 AgentAlign：论文训练集不等于已发布文件

ToolSafe 论文明确训练由 AgentAlign-Traj 673 条和 ASB-Traj 1520 条组成；ASB 仅 academic_search、autonomous_driving、system_admin 三领域用于训练。AgentDojo、AgentHarm 和其他 ASB 领域用于评测。[论文 §3、表2](https://arxiv.org/html/2601.10156v1)

固定仓库 `46358fa424a927a895c6c8322f99032c4eb5155e` 的完整 tree 中，TS-Bench 只有 9 个评测 JSON，未找到上述训练文件。evaluator 确有 `instruction/history/current_action/env_info/score` 字段，但不能因此声称训练数据已发布。README 有 MIT 徽章，却未找到 LICENSE，GitHub license API 返回 null；数据授权待明确。[固定仓库](https://github.com/MurrayTom/ToolSafe/tree/46358fa424a927a895c6c8322f99032c4eb5155e)、[字段代码](https://github.com/MurrayTom/ToolSafe/blob/46358fa424a927a895c6c8322f99032c4eb5155e/src/guardian_evaluator/asb.py)

AgentAlign 固定 HF revision `ddacefcd5f66ef18e814b2f4483c34fdd5eef05c` 发布单 JSON，222074293 bytes，卡片 Apache-2.0；文档有 messages、tools、tool_calls 和 tool_call_id，但没有独立 Alignment 或官方内部划分。论文的有害响应主要为拒绝，良性轨迹来自模拟环境，另混入 ToolACE/Glaive。因此它可作为良性动作候选，不能直接填补间接注入攻击动作；上游条款仍需分别核验，当前不提出大文件下载。[固定卡片](https://huggingface.co/datasets/jc-ryan/AgentAlign/blob/ddacefcd5f66ef18e814b2f4483c34fdd5eef05c/README.md)、[论文 §3.5](https://arxiv.org/html/2505.23020v1)

## SafeMCP：存在训练文件，数据条款仍不明确

SafeMCP：官方仓库 `wlc2424762917/SafeMCP` 有三阶段训练/测试文件，但完整树未找到覆盖 `data_SafeMCP` 的 LICENSE，GitHub license API 返回 null。子项目许可证不能自动覆盖其训练数据。论文称训练另行合成并与评测隔离，同时提及 RLGuard 混合来源；本次不能确认完整来源链，也不能反向断言混入了 AgentHarm 测试请求。暂不下载。已核验 tree SHA `a065fc1854e1d31a6fa98c77cbb0adc723d8d481`，不是 commit SHA，commit 请求因 TLS 失败未固定。[官方仓库](https://github.com/wlc2424762917/SafeMCP)、[论文附录](https://aclanthology.org/2026.acl-long.522.pdf)、[树元数据](https://api.github.com/repos/wlc2424762917/SafeMCP/git/trees/a065fc1854e1d31a6fa98c77cbb0adc723d8d481?recursive=1)

## AgentInjectionBench：可审查的下一阶段范围

- 固定 HF revision `ef230359966c4d87b1c925aa56b8bf6e3f6ffed3`。
- 数据文件 314335 bytes，分类定义 7773 bytes，加 README 与 LICENSE 合计 **351742 bytes（约 0.35 MB）**。文件树 Git blob OID 已记录到提案；它不是 SHA-256，下载后需分别验证和计算本地 SHA-256。
- 作者的 [curate.py](https://huggingface.co/datasets/ppradyoth/AgentInjectionBench/blob/ef230359966c4d87b1c925aa56b8bf6e3f6ffed3/generation/curate.py) 按 attack_category 洗牌后切 70/15/15，seed 默认 42。该固定文件树没有发布 `data/splits/`，不能把 README 示例中的 train 当作已核验的独立官方训练划分。
- 单条分层切分不能证明模板/场景家族隔离。若后续发现同族扩展，先分组再决定派生划分，并标明与上游方案的区别；本阶段不构造 split。
- 审计重点是外泄的资源/目的地、原始授权与越权范围、被操纵的工具参数。执行约束只提供待检查的安全条件，不能直接充当 observed action 或独立 Alignment 标签。
- 保留 Apache-2.0 归属和修改记录。仅本地隔离审计，不执行案例工具、调用模型扩写、接入训练或发布数据。原始测试锁及 candidate 8/v3 均不变。

## 检索与证据边界

使用 nature-academic-search 的 multi-source-search 流程。学术 MCP 未挂载，Conda `intentfence` 的 OpenAlex 备用检索 `indirect prompt injection tool agent dataset` 成功，但首批主要返回已有 InjecAgent 和泛主题论文，未作为新增训练证据。继续检索官方论文、作者 GitHub 与 HF 数据卡，并按论文 ID/仓库身份去重；ToolSafe 与 ToolSafety 是不同工作。

定向检索词包括 `prompt injection agent training dataset tool calls`、`ToolSafe AgentAlign`、`prompt injection training trajectories dataset`。本次为候选筛选，不宣称穷尽性系统综述。两个 agent 分别核验 ToolSafe/AgentAlign 与 SafeMCP，主审核验其余来源并汇总。没有运行来源脚本。

HF/GitHub 直连曾遇到 TLS EOF，经本机代理后部分成功；TraceSafe 固定 README 仍未取到完整正文，因此仅记录其元数据线索，不将访问失败推断为禁止使用。AutoSafe 项目主页的 Dataset 链接实际指向论文页，未据此认定数据已发布。参考：[AutoSafe 主页](https://auto-safe.github.io/)、[官方仓库](https://github.com/Zxy-MLlab/AutoSafe)。

文档、代码及元数据快照保存在忽略目录 `data/interim/candidate_9_source_scan_20260911/`，不含本次新增数据文件。未读取项目锁定测试内容来设计训练样本；公开网页自动展示的非锁定来源示例没有用于样本构造。尚未执行逐样本测试重叠检测，因此不能声明任何新来源通过隔离核验。

本阶段输出为来源比较、明确排除理由和一个小规模审计提案。新增原始数据的条款确认仍依 `configs/execution_policy.yaml`；本阶段确认不被扩展解释为新来源训练或下载批准。
