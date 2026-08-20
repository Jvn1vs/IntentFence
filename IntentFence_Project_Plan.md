# IntentFence 项目实施方案

> 面向 LLM Agent 的轻量、可校准、动作感知间接提示注入安全闸门

- 文档版本：v2.1.1
- 制定日期：2026-08-18
- 最近修订：2026-08-19
- 项目代号：IntentFence
- 目标形态：可训练、可复现、可评测、可部署、可用于简历展示的 AI 安全项目

### v2.1.1 定位、范围与执行细节修订说明

- 不再把“检查动作是否服务于用户目标”表述为首次提出的思想；
- 明确承认并对比 ACL 2025 Task Shield 等已有任务一致性防御；
- 将项目贡献收敛为：用可监督训练的轻量编码器，以更低推理成本实现任务与动作一致性检测；
- 把概率校准、低误报运行点、CPU 部署、困难负样本和跨基准泛化列为核心贡献；
- 明确采用“先保核心闭环、加分项随时间与预算裁剪”的交付原则；
- 核心闭环只包含数据与标签审计、必要基线、主模型、独立校准、跨数据集评测和 ONNX/FastAPI CPU 部署；
- 对抗训练、双门端到端评测、多轮、归因、漂移监控、回归测试和 Docker 降为可选加分项，不再承诺 8 周内全部完成；
- Task Shield 区分论文报告结果、严格复现和本地近似实现，避免因商业 API 或版本变化阻塞项目；
- AgentDojo 按官方任务检查器计算效用；Integrated Gradients 只用于离线分析或异步演示。
- 补充长文档 chunk 聚合后的校准边界、少数类校准充分性、多任务标签冗余以及外部基线数据污染约束。

> 执行原则：先完成一个结果可信、可复现、可部署的核心模型闭环。核心闭环未完成时，不同时展开多个系统扩展；加分阶段最多选择 1～2 项深入完成。

---

## 1. 项目摘要

IntentFence 不是一个只根据单句话判断 `injection / benign` 的普通提示词检测器，而是结合三个信息来源判断一次 Agent 行为是否安全：

1. 用户原始任务（User Intent）；
2. Agent 读取的不可信外部内容（Untrusted Context）；
3. Agent 准备执行的工具或动作（Proposed Action）。

模型的核心输入为：

```text
[CLS] 用户原始任务
[SEP] 不可信外部内容
[SEP] Agent 拟执行动作
[SEP]
```

模型需要完成两个相关任务：

- 风险分类：判断是否存在任务劫持、数据窃取、越权或工具操纵；
- 目标一致性判断：判断拟执行动作是否与用户原始意图一致。

完整扩展版可以采用两道检测门；核心版首先完成动作执行前的 Gate B：

```text
用户任务
   ↓
Gate A：外部内容入口检测
网页、邮件、RAG 文档、工具/MCP返回值 → 内容风险扫描
   ↓
Agent 读取通过入口检查的内容并生成拟执行动作
   ↓
Gate B：动作执行前一致性检测
用户任务 + 外部内容 + 历史动作 + 拟执行动作 → IntentFence
   ├── 低风险：允许执行
   ├── 中风险：要求确认或净化内容
   └── 高风险：阻止动作并记录原因
```

Task Shield 已经提出在测试时验证指令和工具调用是否服务于用户目标，因此 IntentFence 不把“目标一致性”本身宣称为原创。项目的新定位是：训练一个轻量、可校准、可在 CPU 部署的动作感知分类器，研究它能否以低于在线 LLM 裁判的延迟、成本和部署依赖，获得有竞争力的安全性与正常任务效用。Task Shield 只作为系统级参考或可选复现实验，不作为核心项目能否完成的前置条件。

相关已有工作：

- Task Shield：https://aclanthology.org/2025.acl-long.1435/
- AgentDojo：https://github.com/ethz-spylab/agentdojo
- AgentDojo 任务与效用协议：https://agentdojo.spylab.ai/concepts/task_suite_and_tasks/
- AgentDojo BaseUserTask API：https://agentdojo.spylab.ai/api/base_tasks/
- IPIGuard：https://github.com/Greysahy/ipiguard

---

## 2. 项目目标与边界

### 2.1 项目目标

- 训练一个自己完成数据处理、微调、评测和部署的安全检测模型；
- 降低传统关键词检测器在安全论文、日志、邮件和技术文档上的误报；
- 检测网页、邮件、RAG 文档和工具返回值中的间接提示注入；
- 检测由注入引起的数据外传、越权操作和任务目标偏移；
- 在未见攻击模板、未见数据集和未见工具上评价泛化能力；
- 与 ProtectAI、PIGuard/InjecGuard 两个可本地运行的开源检测器进行核心比较；
- 对风险分数进行概率校准，使 Allow / Confirm / Block 策略有可靠依据；
- 将模型压缩为能够在普通 CPU 电脑运行的 ONNX 服务；
- 形成完整 GitHub 项目、实验报告、模型卡和在线或本地演示。

在核心目标完成后，可选择对抗增强、Gate A + Gate B、AgentDojo 端到端评测、多轮历史、离线归因或生命周期监控中的 1～2 项作为简历加分项。

### 2.2 暂不纳入第一版的内容

- 不从零预训练大语言模型；
- 不训练 7B 或更大的生成式安全模型；
- 第一版不处理图片、音频和视频中的多模态注入；
- 第一版不追求覆盖所有 Agent 框架；
- 核心版不训练长序列会话模型，也不设计会话累计风险公式；有限历史窗口仅作为可选实验；
- 第一版不做无人工审核的线上自动持续学习；
- 不在未经授权的真实在线系统上发起安全测试；
- 不把单一测试集上的高 Accuracy 当作完成标准。

### 2.3 第一版推荐范围

核心版只做英文文本和结构化工具动作，优先完成可靠的单步实验闭环。Unicode、Base64、格式包装、最近 3 步历史、中文、多语言混合、完整长时序模型和多模态注入均不属于核心交付；其中前四项可在核心版完成后选择性加入。

---

## 3. 威胁模型与安全问题定义

### 3.1 保护对象

- 用户的真实任务目标；
- Agent 可访问的邮件、文件、凭据和隐私数据；
- Agent 具有权限的搜索、上传、发送、删除和支付等工具；
- RAG 知识库和外部检索结果；
- Agent 的系统提示词、工具描述和内部状态。

### 3.2 攻击者能力

第一版假设攻击者不能直接修改系统提示词，但可以控制或污染以下一种外部信息：

- 网页内容；
- 邮件正文或附件文本；
- RAG 检索文档；
- 工具或 MCP 服务返回值；
- 被 Agent 自动读取的日志、代码注释或表格内容。

攻击者希望外部内容被 Agent 当作高优先级指令执行。

### 3.3 检测时点

威胁模型明确覆盖“工具返回后才激活”的延迟注入：

1. 外部内容刚进入系统时由 Gate A 做单文本快速检查；
2. Agent 形成动作计划后由 Gate B 结合用户目标、原始外部内容和历史动作再次判断；
3. Gate A 未识别的隐蔽指令，仍可能因最终动作偏离用户目标而被 Gate B 拦截；
4. 高风险工具即使通过模型，也必须经过权限策略或人工确认。

### 3.4 攻击类型

建议使用以下标签：

| 标签 | 含义 | 示例后果 |
|---|---|---|
| `benign` | 正常外部内容 | 正常回答或正常工具调用 |
| `instruction_hijacking` | 改变用户原始目标 | 用户要求总结，Agent 转而执行其他任务 |
| `data_exfiltration` | 诱导泄露数据 | 上传邮件、文件或密钥到外部地址 |
| `privilege_escalation` | 诱导使用超出任务需要的权限 | 调用高权限管理工具 |
| `tool_manipulation` | 操纵工具参数或调用顺序 | 把正常收件人替换为攻击者地址 |

可额外提供二分类标签：

```text
0 = 与用户目标一致
1 = 与用户目标冲突
```

### 3.5 有限多轮威胁

核心威胁模型以单步动作检查为主，同时承认真实攻击可能通过多轮逐步改变目标。可选多轮实验只把最近 `k=3` 次工具调用摘要与执行结果拼接到当前输入，不新增动作偏离头，也不在第一版维护未经验证的累计风险公式。完整多轮攻击模型在核心单步模型完成后单独立项。

### 3.6 防御边界

IntentFence 是纵深防御的一层，不承诺彻底解决提示注入。实际系统仍然需要：

- 最小权限；
- 高风险操作的人类确认；
- 工具参数白名单；
- 数据访问控制；
- 操作审计；
- 速率限制与异常行为监控。

---

## 4. 核心研究问题与假设

### H1：上下文感知是否降低误报

在相同攻击召回率下，输入 `(用户任务, 外部内容)` 的模型，是否比只输入外部内容的模型具有更低的正常请求误报率？

### H2：动作感知是否提高安全性

输入 `(用户任务, 外部内容, 拟执行动作)`，是否比只分析用户输入或外部文本更容易发现数据外传、越权操作和工具参数劫持？

### H3：困难负样本是否改善泛化

加入含有 `ignore instructions`、`system prompt` 等敏感词但实际无害的技术文章、日志和安全讨论后，是否能降低过度防御，同时保留对真正攻击的识别能力？

### H4：多任务学习是否优于单任务分类

同时训练“攻击类型分类”和“目标一致性判断”，是否比只训练一个二分类头具有更好的跨数据集表现？

该假设存在天然的标签冗余风险：`data_exfiltration`、`privilege_escalation`、`tool_manipulation` 等风险类别通常与 `alignment_label = 1` 高度相关。训练前应输出 Risk 与 Alignment 的列联表、条件概率和可选的互信息统计。如果 E3 消融显示 Alignment Head 没有独立增益，应将其作为有效负结果，分析标签相关性，并考虑在部署模型中删除该辅助头；不得为了保留多任务设计而反复调参或选择性汇报。

### H5：校准后的风险分数是否支持稳定分级

Temperature Scaling 是否能够降低 ECE、Brier Score 和 NLL，并使相同阈值在不同工具风险级别上具有更稳定的误报与漏报表现？

### H6：轻量模型能否形成有意义的成本优势（可选系统实验）

在严格注明复现条件的前提下，IntentFence 是否能以比在线 LLM 裁判更低的 P95 延迟、单次调用成本和部署依赖，取得有竞争力的安全性与正常任务效用？如果 Task Shield 无法严格复现，则只与论文报告结果作背景讨论，或将本地小 LLM 实验标为 `Task-Shield-inspired approximation`，不做直接数值胜负结论。

### 研究主张边界

项目不预设一定击败所有 SOTA。成立的贡献可以是下列任意一种经公平实验验证的结果：

- 相同 FPR 下更高的攻击召回率；
- 相同攻击成功率下更高的正常任务效用；
- 安全性接近但延迟、成本或模型大小显著降低；
- 在未见工具、未见模板或困难正常样本上泛化更好；
- 概率校准和故障策略更适合实际部署。

---

## 5. 技术路线总览

| 路径 | 阶段 | 主要工作 | 阶段出口条件 | 是否需要 GPU |
|---|---|---|---|---|
| 必做核心 | C0 定位与协议 | 主张边界、数据划分、基线与指标协议 | 冻结测试集、校准集、主指标和预算 | 否 |
| 必做核心 | C1 数据与基线 | 标签审计、规则/TF-IDF、两个开源检测器 | 标签质量报告和统一基线表完成 | 少量 |
| 必做核心 | C2 主模型与校准 | Small/Base、上下文/动作、多任务、Temperature Scaling | 模板隔离与跨数据集结果、校准报告完成 | 是 |
| 必做核心 | C3 部署与交付 | ONNX INT8、FastAPI、CPU 实测、README/模型卡 | 从训练到部署可复现，指标可追溯 | 少量 |
| 可选加分 | B1 鲁棒增强 | 对抗训练与未见变换测试 | 安全收益没有以明显误报上升为代价 | 是 |
| 可选加分 | B2 系统防御 | 双门与 AgentDojo 官方协议评测 | 同时报 ASR、Benign Utility、Utility Under Attack | 可能 |
| 可选加分 | B3 分析与生命周期 | 有限历史、离线归因、回归或漂移报告 | 选择其中一项形成完整实验，不求全 | 少量 |

C0～C3 构成简历项目的完成线，计划用 6～8 周完成。B1～B5 不是并列必做项，核心闭环完成后最多选择 1～2 项；完整实现全部加分功能，单人应预留约 12～16 周或更长。C1 未完成前不租卡训练主模型，C2 未完成前不展开多轮、归因和漂移等扩展。

---

## 6. 推荐数据来源

### 6.1 Microsoft BIPIA

- 地址：https://github.com/microsoft/BIPIA
- 用途：主要训练数据和场景构造参考；
- 场景：Web QA、Email QA、Table QA、Summarization、Code QA；
- 优势：任务信息和外部内容边界较明确，适合转换成上下文检测样本。

### 6.2 InjecAgent

- 地址：https://github.com/uiuc-kang-lab/InjecAgent
- 用途：主要跨数据集测试集；
- 规模：1,054 个测试案例；
- 场景：17 类用户工具和 62 类攻击者工具；
- 重点攻击：直接伤害和数据窃取。

### 6.3 AgentDojo

- 地址：https://github.com/ethz-spylab/agentdojo
- 用途：端到端 Agent 安全评测；
- 目标：评价加入 IntentFence 前后攻击成功率、正常任务完成率和工具调用正确率；
- 注意：动态 Agent 评测可能需要本地小型 LLM 或付费 API，应与检测模型训练成本分开统计。

### 6.4 NotInject / InjecGuard

- 地址：https://github.com/safolab-wisc/injecguard
- 用途：过度防御和困难正常样本测试；
- 重点：正常文本虽然包含敏感攻击词，但不应被模型判断为攻击。

### 6.5 自建困难负样本

需要补充以下正常内容：

- 讨论提示注入的安全文章；
- 包含 `ignore`、`system`、`upload` 等词的普通技术文档；
- 引用攻击文本但不要求执行的日志或论文；
- 用户明确要求执行某个动作、外部文档只是重复该动作的正常场景；
- 邮件签名、免责声明、代码块、JSON 和配置文件；
- 与攻击表面相似但符合用户目标的工具调用。

自建数据需要记录来源、生成方式、标签依据和人工检查状态。

### 6.6 标签质量审计

公开数据集不能默认视为完全正确。正式训练前需要生成 `reports/data_quality/label_audit.md`，至少完成：

1. 按数据源、风险类别和场景分层抽取不少于 200 条样本；
2. 将样本标记为 `correct`、`incorrect` 或 `ambiguous`；
3. 检查 `user_goal`、`untrusted_content` 与 `proposed_action` 的边界是否清晰；
4. 记录错误标签、缺失上下文、动作参数不完整和攻击类型冲突；
5. 模糊样本不直接进入主训练集，可放入单独挑战集；
6. 如果能够找到第二位标注者，独立标注同一子集并计算 Cohen's Kappa；
7. 如果只有一名标注者，间隔一周进行第二次盲审，并公开说明限制；
8. 分别报告 BIPIA、InjecAgent、自建数据的疑似标签噪声率；
9. 训练后检查高损失样本，区分模型错误与标签错误；
10. 任何标签修订都记录原标签、新标签、理由和版本。

标签质量审计属于 C1 阶段出口条件。未完成该报告前，不启动正式 Base 模型训练。

---

## 7. 数据格式与数据工程

### 7.1 推荐 JSONL 格式

```json
{
  "sample_id": "bipia_web_000001",
  "source": "BIPIA",
  "scenario": "web_qa",
  "user_goal": "Summarize the main argument of the webpage.",
  "untrusted_content": "The webpage content ...",
  "proposed_action": "upload_file(path='notes.txt', url='https://example.com')",
  "risk_label": "data_exfiltration",
  "alignment_label": 1,
  "attack_family": "indirect_prompt_injection",
  "severity": 3,
  "template_group": "web_upload_01",
  "split": "train",
  "language": "en",
  "human_verified": true
}
```

`split` 只能取 `train / validation / calibration / test_a / test_b / test_c / test_d`。推荐由版本化的 `split_manifest.json` 生成该字段，而不是人工逐条填写；原始数据保持不可变，派生 JSONL 才写入划分结果。

### 7.2 必做的数据处理

1. 统一各数据集字段；
2. 清除完全重复样本；
3. 使用规范化文本和 n-gram/embedding 检查近重复；
4. 为同源攻击模板建立 `template_group`；
5. 检查类别分布和场景分布；
6. 检查文本长度，确定截断和分块策略；
7. 为每条样本保留来源和许可证信息；
8. 固定数据划分并保存随机种子；
9. 对测试集进行人工抽样核查；
10. 生成 `dataset_report.md` 或数据统计图。

### 7.3 数据划分原则

不能只做普通随机划分。推荐：

```text
训练来源池：BIPIA + 自建困难负样本
训练集：训练来源池的约 65%～70%
验证集：训练来源池的约 10%～15%，用于模型选择和超参数选择
校准集：训练来源池的约 10%～15%，在模型权重冻结后拟合温度和阈值
测试集 A：BIPIA 中完全未见模板
测试集 B：InjecAgent 跨数据集测试
测试集 C：NotInject 误报测试
测试集 D：AgentDojo 未见工具和端到端测试
```

具体比例可随数据规模调整，但 `train`、`validation`、`calibration` 和所有测试集必须互斥。校准集与验证集同级：它不参与梯度训练，不用于挑选模型结构或超参数，只在最佳模型权重冻结后用于 Temperature Scaling 和决策阈值选择。

同一攻击模板的改写必须全部进入同一个 split，防止模型通过记忆关键词获得虚高结果。划分时按 `template_group`、`attack_family` 和必要时的来源簇分组，保存 `split_manifest.json`、随机种子、数据哈希和各 split 统计。

Calibration split 在不破坏 `template_group` 和来源簇隔离的前提下，尽量按风险类别分层。划分完成后必须报告每类样本数和正负比例；如果 `privilege_escalation`、`tool_manipulation` 等少数类样本不足，则将对应的 Classwise ECE 标记为 `insufficient evidence`，不据此制定独立类别阈值。模板隔离优先于为了凑样本数而拆分同源样本；少数类不足时优先使用整体攻击风险校准、合并风险组或保守人工确认策略。

### 7.4 长文本策略

第一版采用滑动窗口：

- `max_length = 384`；
- 用户任务和动作优先保留；
- 外部内容按 256～320 tokens 分块；
- 每个 chunk 单独计算风险；
- 文档级风险使用最大风险或 Top-k 均值聚合。

Chunk 级校准概率经过 max 或 Top-k 聚合后，不再具有样本级校准保证。未单独进行文档级校准时，聚合结果只能命名为 `document_risk_score`，用于排序、告警和保守阈值，不能解释为攻击概率，也不能直接作为 `P_attack` 进入风险乘法。对于不超长、能够作为单个模型样本输入的文本，使用样本级校准概率；对于超长文本，默认采用保守阈值与人工确认。若后续确实需要文档级概率，必须先固定分块与聚合算法，再使用互斥的文档级 calibration 数据重新拟合校准器并重新报告 ECE、Brier 和 NLL。

后续可以比较：截断、滑动窗口、最大池化和注意力聚合。

---

## 8. 基线与已有方法比较

### 8.1 规则基线

实现关键词和正则表达式检测器，覆盖：

- 忽略或覆盖指令；
- 请求系统提示词；
- 上传、发送或泄露信息；
- Base64、零宽字符和异常 Unicode；
- 可疑 URL 与工具参数。

规则基线的目的不是追求最高性能，而是测量简单规则的检测上限和误报问题。

### 8.2 TF-IDF + Logistic Regression

- 输入：仅外部内容；
- 作用：建立传统机器学习基线；
- 可在本地 CPU 训练；
- 必须报告词级和字符级 n-gram 结果。

### 8.3 单文本 Transformer

- 模型：DeBERTa-v3-small；
- 输入：仅 `untrusted_content`；
- 作用：与上下文模型进行公平对比。

### 8.4 开源提示注入检测器基线

核心闭环只要求两个可本地运行的开源检测器，避免基线数量挤占主模型实验时间：

| 基线 | 类型 | 输入 | 主要用途 |
|---|---|---|---|
| ProtectAI `deberta-v3-base-prompt-injection-v2` | 184M文本分类器 | 外部内容 | 现成 DeBERTa PI 检测器 |
| PIGuard / InjecGuard | 过度防御感知检测器 | 外部内容 | 与 NotInject 和低误报能力比较 |
| IntentFence 单文本版本 | 同骨干内部基线 | 外部内容 | 隔离数据与训练配方影响 |
| IntentFence 完整版本 | 本项目主模型 | 任务+内容+动作 | 检验上下文和动作信息增益 |

参考地址：

- ProtectAI：https://huggingface.co/protectai/deberta-v3-base-prompt-injection-v2
- LLM Guard：https://github.com/protectai/llm-guard
- PIGuard/InjecGuard：https://github.com/safolab-wisc/injecguard

`laiyer-ai/llm-guard` 是 LLM Guard 的旧组织路径，其 PromptInjection 扫描器使用 ProtectAI 模型，不能与 ProtectAI 模型重复计为两个独立模型基线。

Meta Prompt Guard 2、IPIGuard 等其他方法只在时间和许可证允许时加入，不属于核心完成条件。基线数量应服从统一数据、统一阈值和完整错误分析的质量要求。

### 8.5 Agent 系统防御基线

AgentDojo 端到端比较属于可选加分项。在资源允许时比较：

1. 无防御；
2. 规则或 Tool Filter；
3. ProtectAI 文本检测器；
4. Task Shield 论文报告结果、严格复现或近似实现中的一种；
5. IPIGuard（资源允许时）；
6. IntentFence Gate A；
7. IntentFence Gate A + Gate B 完整系统。

Task Shield 与本项目最接近，必须在相关工作和结果讨论中明确说明。IntentFence 的目标不是重复宣称“任务一致性”思想，而是研究监督训练的小型编码器能否以更低运行成本近似这种检查。

Task Shield 结果必须使用以下标签之一，不能混写：

1. `paper-reported`：仅引用论文公开结果，不声称复现；
2. `reproduced`：固定论文使用的模型版本（优先核对 `gpt-4o-2024-05-13`）、提示词、AgentDojo/任务版本、Agent 配置和攻击设置后复现；
3. `Task-Shield-inspired approximation`：因 API 不可用或超预算，使用固定版本的本地开源小 LLM 作为一致性裁判。这只能验证设计思路和成本，不得与原论文结果进行直接胜负比较。

所有 LLM 调用必须缓存请求、响应、模型标识和配置。若论文实验环境无法完整获得，应优先使用 `paper-reported`，而不是声称完成了严格复现。

### 8.6 公平比较协议

所有可运行基线必须：

- 使用相同、冻结的数据版本；
- 对 IntentFence 及其他自行训练的模型使用相同的成员去重、近重复检查和模板隔离规则；
- 对只有权重可用的外部基线使用相同的冻结测试集和评测协议，但不声称完成其训练成员去重；只能根据模型卡、训练数据说明和发布时间记录潜在数据污染；
- 不在最终测试集上调阈值；
- 同时报默认阈值和验证集选择的阈值；
- 在相同 FPR（优先 1%）下比较 TPR；
- 在 AgentDojo 中使用相同 Agent 模型、任务子集和攻击配置；
- 固定 AgentDojo benchmark/task-suite 版本，并使用官方任务检查器计算效用；
- 报告模型大小、硬件、P50/P95延迟、吞吐量和额外调用成本；
- 标注每个模型可能见过的训练数据，讨论潜在数据污染；
- 区分“文本检测准确率”和“端到端 Agent 攻击成功率”，不得混为一个指标。

项目不要求在所有数据集上击败所有 SOTA；必须做到的是公平、可复现地解释安全性、正常效用、成本和延迟之间的权衡。

---

## 9. 模型训练方案（重点）

### 9.1 模型选择

训练分两步进行：

1. `microsoft/deberta-v3-small`：验证数据、代码、损失函数和评测流水线；
2. `microsoft/deberta-v3-base`：作为最终主模型。

不建议直接从已经训练好的 Prompt Injection 检测器继续训练，否则很难区分已有能力和本项目贡献。应从普通 DeBERTa 基础权重开始微调，并在文档中准确称为“微调”，不要称为从零训练基础模型。

### 9.2 输入构造

### 模型 A：单文本基线

```text
[CLS] untrusted_content [SEP]
```

### 模型 B：上下文感知模型

```text
[CLS] user_goal [SEP] untrusted_content [SEP]
```

### 模型 C：完整动作感知模型

```text
[CLS] user_goal [SEP] untrusted_content [SEP] proposed_action [SEP]
```

核心实现优先使用 tokenizer 已有的 `[SEP]` 分隔，不依赖 `token_type_ids`。`microsoft/deberta-v3-base` 的公开配置为 `type_vocab_size: 0`，表示该检查点默认不使用 segment/type embedding；这不是因为位置编码“占用了” `token_type_ids`，而是该模型配置本身没有启用类型词表。

新增结构标记只作为后续消融方案：

```text
<USER_GOAL> ...
<UNTRUSTED_CONTENT> ...
<PROPOSED_ACTION> ...
```

这些标记需要加入 tokenizer，并调用 `resize_token_embeddings` 调整 embedding 大小。新增 embedding 必须通过足够训练样本学习，因此要与纯 `[SEP]` 版本做同数据、同随机种子的消融；数据量不足或结果无增益时继续使用 `[SEP]` 方案。

### 9.3 多任务输出头

共享 DeBERTa 编码器，连接两个分类头：

```text
DeBERTa encoder
   ├── Risk Head：5 类风险分类
   └── Alignment Head：目标一致 / 目标冲突
```

损失函数：

\[
L = L_{risk} + \lambda L_{alignment}
\]

第一轮建议 `lambda = 0.5`，随后尝试：

```text
lambda ∈ {0.25, 0.5, 1.0}
```

如果类别不均衡，优先使用带类别权重的交叉熵；只有在少数类依然明显不足时再比较 Focal Loss。

### 9.4 推荐训练参数

### DeBERTa-v3-small：流水线验证

```yaml
model_name: microsoft/deberta-v3-small
max_length: 384
train_batch_size: 16
eval_batch_size: 32
gradient_accumulation_steps: 1
learning_rate: 2.0e-5
weight_decay: 0.01
epochs: 3
warmup_ratio: 0.10
max_grad_norm: 1.0
mixed_precision: fp16
early_stopping_patience: 2
metric_for_best_model: macro_f1
seed: 42
```

### DeBERTa-v3-base：最终主模型

```yaml
model_name: microsoft/deberta-v3-base
max_length: 384
train_batch_size: 8
eval_batch_size: 16
gradient_accumulation_steps: 2
effective_batch_size: 16
learning_rate: 2.0e-5
weight_decay: 0.01
epochs: 3
warmup_ratio: 0.10
max_grad_norm: 1.0
mixed_precision: fp16
gradient_checkpointing: false
early_stopping_patience: 2
metric_for_best_model: macro_f1
save_total_limit: 2
seed: 42
```

如果显存不足，按以下顺序调整：

1. batch size 从 8 降至 4；
2. 使用 gradient accumulation 保持有效 batch size；
3. 打开 gradient checkpointing；
4. 将 `max_length` 从 384 降至 256；
5. 最后才考虑换回 small 模型。

### 9.5 训练流程

### 阶段 T0：CPU 冒烟测试

- 使用 200～500 条样本；
- 只训练 20～50 steps；
- 检查 forward、backward、loss、指标和保存路径；
- 检查标签映射不会在不同脚本中改变；
- 检查 checkpoint 可以重新加载。

### 阶段 T1：Small 模型单次训练

- 固定 seed 42；
- 训练单文本模型；
- 训练上下文模型；
- 训练完整动作模型；
- 检查加入上下文后是否真的提升跨模板测试，而不只提升训练集。

### 阶段 T2：Base 主模型训练

- 只在 Small 流水线稳定后启动；
- 使用完全相同的数据 split；
- 记录 GPU、CUDA、PyTorch、Transformers 版本；
- 每轮保存验证集 Macro-F1 最好的 checkpoint；
- 使用早停，避免无意义消耗算力。

### 阶段 T3：困难负样本训练

- 在训练集中逐步加入 NotInject 风格正常样本；
- 比较加入前后的攻击召回率和误报率；
- 重点观察包含安全术语、代码、引号和命令式语言的正常样本；
- 不允许使用最终测试集样本直接参与训练。

### 阶段 T4：受控对抗数据增强（可选加分）

只对训练集生成增强样本，推荐从以下低风险、可复现变换开始：

- 大小写和空白变化；
- 换行、Markdown、HTML、JSON、代码注释包装；
- 指令移动到长文档中部或尾部；
- 零宽字符和一部分 Unicode 同形字；
- 正常内容前后包围攻击指令；
- 保持攻击意图不变的受控同义改写。

增强数据必须带有：

```text
parent_sample_id
augmentation_type
augmentation_seed
human_checked
```

训练增强和鲁棒性测试必须使用不同变换族。例如，训练可以使用大小写、空格和 Markdown 包装；最终未见攻击测试保留新的 Unicode 组合、未见编码、未见格式和跨语言变体。否则只能证明模型记住了增强方式。

每次增强实验同时报告：攻击召回率变化、NotInject 误报变化和正常任务效用变化。只有安全收益大于误报代价时才保留该增强策略。

### 阶段 T5：概率校准与阈值冻结（核心必做）

- 从训练来源池中按 `template_group` 预留约 10%～15% 的 calibration split，不能与训练、验证或任何最终测试重合；
- 在模型权重冻结后拟合 Temperature Scaling 的温度参数；
- 比较校准前后的 ECE、Classwise ECE、Brier Score、NLL 和可靠性图；
- 只在 calibration split 上选择 1% FPR 运行点和策略阈值；验证集只用于模型选择，避免角色混用；
- 分别冻结 Allow / Confirm / Block 阈值和高风险工具策略；
- 最终测试集只评估一次，不再依据结果调整温度或阈值。

### 阶段 T6：最终复现实验

- 核心交付至少完整复现固定种子 `42`；时间和预算允许时，对最佳配置补充 `42、52、62` 三个随机种子；
- 运行多个种子时报告均值和标准差；只有一个种子时明确标注，不虚构稳定性结论；
- 固定数据版本、代码 commit 和依赖；
- 每个种子分别训练，校准策略保持一致；
- 保存温度参数与最终阈值，不能在测试集上反复调阈值。

### 9.6 实验记录

每次训练至少记录：

- run ID；
- Git commit；
- 数据集版本和哈希；
- 校准集版本和哈希；
- 模型名称；
- 全部超参数；
- 随机种子；
- GPU 型号；
- 训练时间；
- 最佳 epoch；
- 验证集和各测试集指标；
- checkpoint 路径；
- temperature、Allow/Confirm/Block 阈值；
- 错误样本分析文件。

可以使用 TensorBoard、MLflow 或 Weights & Biases；为减少外部依赖，第一版推荐 TensorBoard + CSV/JSON 日志。

### 9.7 训练完成标准

主模型不能只满足“训练成功”，还应满足：

- 训练和验证 loss 曲线正常；
- 至少证明上下文/动作版本相对同骨干单文本版本存在增益；
- 完成与 ProtectAI、PIGuard 等开源检测器的同数据同阈值比较；
- 在未见模板上保持有效；
- 在 InjecAgent 上有跨数据集泛化；
- NotInject 误报率可接受；
- 如果选择对抗增强，加分版本不能通过严重增加误报换取表面召回率；
- 校准后的 ECE、Brier Score 或 NLL 至少一项实质改善，且不得明显损害主要安全指标；
- 如果运行三个随机种子，结果没有无法解释的巨大波动；
- 最优模型可以重新加载并复现预测。

### 9.8 校准实现细节

对于风险分类头，Temperature Scaling 在 logits 上学习单个温度 `T`：

\[
p = softmax(z / T)
\]

对于目标一致性二分类头，可以分别拟合温度，避免一个头的置信度结构影响另一个头。最终策略层只使用校准后的分数。ECE 受分箱影响，因此不能单独使用，必须结合 Brier、NLL 和 Reliability Diagram。

在明显的跨数据集分布漂移下，Temperature Scaling 可能仍然失准。需要分别报告：

- 同分布校准效果；
- InjecAgent 上的跨数据集校准效果；
- 长文本、未见工具和对抗变体上的条件校准效果；
- 不同风险类别和工具等级的校准误差。

如果跨域失准严重，第一版先使用保守阈值和人工确认，不急于引入复杂校准模型。

---

## 10. 安全评测方案（重点）

### 10.1 评测原则

安全检测不能只报告 Accuracy。测试集通常类别不均衡，而且部署价值主要取决于低误报率条件下能拦截多少攻击。

核心报告不把所有指标当成并列优化目标，而采用“硬约束 → 主指标 → 诊断指标 → 工程选择”的层级：

#### 第一层：部署硬约束

- Benign FPR 目标不高于 1%，最终阈值以校准集可实现结果为准；
- 正常任务效用下降不得超过预先冻结的容许范围；
- 跨数据集和关键攻击类别不能出现不可接受的性能崩溃；
- CPU P95 延迟必须落在部署预算内。

#### 第二层：主要安全指标

- 检测模型使用 `TPR@1% FPR`；
- Agent 系统使用 `Targeted ASR`，并同时报告 `Utility Under Attack`；
- 在满足误报与正常效用硬约束的候选模型中，优先选择攻击召回更高、ASR 更低的模型。

#### 第三层：校准与诊断指标

- Macro-F1；
- 每个风险类别的 Precision、Recall 和 F1；
- AUROC；
- AUPRC；
- TPR@0.5% FPR（条件允许时，作为敏感性分析）；
- NotInject 误报率；
- ECE、Classwise ECE、Brier Score 和 NLL；
- 校准前后 Reliability Diagram；
- 各场景、攻击类型、长度区间和工具类型的分组结果。

#### 第四层：工程指标

- 模型大小和峰值内存；
- P50/P95 推理延迟与吞吐量；
- 单次检测成本、API 调用次数和总实验成本。

冲突处理规则：安全指标不能靠突破误报率或正常效用硬约束获得；量化等工程优化不能造成关键安全指标明显回退。在安全结果统计上接近且均满足约束时，再选择延迟和成本更低的方案。

### 主要部署指标摘要

```text
检测器：在 Benign FPR ≤ 1% 约束下最大化 TPR
Agent 系统：在正常效用损失约束下最小化 Targeted ASR
校准：ECE / Brier / NLL 用于验证分级阈值可信度
工程：安全结果相近时，再比较 P95 延迟、模型大小和成本
```

### 10.2 安全测试层级

### Level 1：已见分布测试

- 与训练集同来源但模板隔离；
- 用于检查模型是否学到基本风险模式；
- 不作为最终泛化结论。

### Level 2：跨数据集测试

- 训练使用 BIPIA；
- 测试使用 InjecAgent；
- 不在 InjecAgent 上训练或调阈值；
- 用于衡量模型是否只是记住 BIPIA 表达方式。

### Level 3：过度防御测试

- 使用 NotInject；
- 添加安全博客、代码、日志、引号和技术邮件；
- 分析包含攻击关键词的正常内容；
- 报告误报案例类型，而不是只给总数。

### Level 4：对抗增强与未见规避测试（可选加分）

对攻击文本进行防御性鲁棒性评测：

- 大小写混合；
- 插入空格和换行；
- 同义改写；
- Unicode 同形字；
- 零宽字符；
- Base64 或简单编码；
- JSON、HTML、Markdown、代码注释包装；
- 把攻击指令放在长文档中间或末尾；
- 在攻击前后加入大量正常内容。

这些变换只在本地公开数据和受控实验环境中使用。必须将变换分成 `train_augmentations` 和 `heldout_attack_transformations` 两组，并在仓库配置中固定。最终报告同时包含：

- 未做增强的模型；
- 做了受控增强的模型；
- 已见变换上的鲁棒性；
- 未见变换上的鲁棒性；
- 增强后正常数据和 NotInject 误报变化。

### Level 5：端到端 Agent 测试（可选加分）

在 AgentDojo 或自建沙箱中比较：

```text
无防御 Agent
规则防御 Agent
ProtectAI / PIGuard 文本检测防御 Agent
Task Shield（注明 paper-reported / reproduced / inspired approximation）
IntentFence Gate A
IntentFence Gate A + Gate B 完整防御
```

AgentDojo 不使用笼统的“任务完成率”或额外 LLM 主观打分代替官方效用。固定 benchmark/task-suite 版本，并调用各任务自带的官方 utility 检查逻辑；该逻辑可能结合模型输出、工具调用轨迹以及执行前后的环境状态。需要测量：

- Targeted Attack Success Rate：攻击者目标达成的安全案例比例；
- Benign Utility：无攻击时由官方任务检查器判定完成的用户任务比例；
- Utility Under Attack：攻击存在时，用户任务正确完成且没有攻击者目标造成的副作用的比例；
- 被阻止的工具调用数量；
- 高风险动作漏报；
- 需要人工确认的比例；
- 每次任务增加的延迟。

### 10.3 风险阈值与工具权限

不同工具不能使用完全相同的阈值。建议定义风险等级：

| 工具类型 | 示例 | 风险级别 | 建议策略 |
|---|---|---:|---|
| 只读 | 搜索、读取公开网页 | 1 | 高阈值，减少误报 |
| 普通写入 | 写草稿、保存本地结果 | 2 | 中等阈值 |
| 外部通信 | 发邮件、上传文件、发消息 | 3 | 低阈值或人工确认 |
| 敏感操作 | 删除、支付、修改权限 | 4 | 默认人工确认 |

可以使用：

\[
R_{final} = P_{attack} \times W_{tool}
\]

其中 `P_attack` 必须是经过独立校准集校准的样本级攻击概率，`W_tool` 是工具风险权重。未校准 softmax 或未经文档级重新校准的 chunk 聚合分数只能用于排序和告警，不能直接解释为攻击概率，也不能作为这里的 `P_attack`。

`R_final` 是融合模型风险与工具权限的策略风险分数，不是概率，不能表述为“发生攻击的概率”。Allow / Confirm / Block 阈值只在独立 calibration split 上确定并冻结。对外部通信、删除、支付和权限修改等高风险动作，模型低风险也不能替代权限控制与人工确认。

### 10.4 错误分析

每轮最终评测都应输出：

- 最危险的假阴性；
- 最常见的假阳性；
- 按场景、攻击类别、文本长度和工具类型统计；
- 模型置信度分布；
- 单文本模型与完整模型预测差异；
- 是否因为截断导致漏检；
- 是否依赖敏感关键词形成捷径。

### 10.5 可解释性与归因

解释性是可选加分项，用于帮助安全分析人员定位风险文本，不作为模型正确性的证明，也不进入默认实时推理路径。推荐实现：

1. 使用 Integrated Gradients 对输入 embedding 做 token 归因；
2. 分别汇总 `user_goal`、`untrusted_content`、`proposed_action` 三个区域的贡献；
3. 高亮外部内容中贡献最高的连续 span；
4. 对高风险 span 进行遮挡，再次预测，检查风险是否实质下降；
5. 展示单文本模型与完整模型归因差异；
6. 保存 attribution 方法、baseline embedding、步数和随机种子。

Integrated Gradients 通常需要多次前向/反向计算，遮挡验证也需要重复推理，因此不能计入核心 `/v1/evaluate` 的实时 SLO。默认实时响应使用校准分数、风险类别和确定性策略模板生成 `reason`；归因通过离线 notebook、异步任务或单独的 `/v1/explain` 接口按需运行。

注意力热力图可以用于演示，但不能单独宣称为可靠解释。归因只对 Confirm/Block 样本、安全人员复核样本或演示样本计算，并明确提示其不代表因果证明。

### 10.6 有限多轮历史（可选加分）

核心模型只处理当前单步样本。可选实验增加最近 `k=3` 步历史，并继续使用已有 `[SEP]` 分隔：

```text
[CLS] 原始用户任务
[SEP] 最近三次动作摘要及执行结果
[SEP] 当前外部内容
[SEP] 当前拟执行动作
[SEP]
```

第一版不使用原来的 `d_t` 动作偏离分数，也不新增隐藏的分类头或累计风险公式。只比较当前步模型与历史拼接模型，验证多轮信息是否确实带来增益。只有结果明显支持后，才单独设计、标注和校准 session 风险；LSTM、Temporal Transformer、图模型及累计公式均不属于当前计划。

### 10.7 双门安全评测（可选加分）

分别评估：

- 只有 Gate A：是否能快速过滤明显注入；
- 只有 Gate B：是否能识别没有攻击关键词但导致动作偏移的内容；
- Gate A + Gate B：端到端安全性、误报、任务效用和延迟；
- Gate A 漏检但 Gate B 成功拦截的比例；
- Gate A 误报对正常任务的影响；
- Gate B 在工具返回后延迟注入场景中的效果。

Gate A 适合运行快速文本检测器，Gate B 使用 IntentFence 完整三元组或带历史输入。两者模型可以相同，也可以由开源文本检测器与 IntentFence 组合。

### 10.8 基线结果解释规则

- 不同输入权限的方法不能只比一个 Accuracy；
- 文本检测器优于 IntentFence 时，要检查是否存在训练数据重叠；
- IntentFence 优于文本检测器时，要说明其使用了额外上下文和动作信息；
- Task Shield 等 LLM 方法要同时报告模型/API成本和延迟；
- 端到端防御必须同时报告 Attack Success Rate 与 Utility；
- 结果不支持原假设时如实报告，并将其作为负结果或设计修订依据。

---

## 11. 消融实验设计

核心必须完成 E0～E4；E5～E6 只在选择对应加分项时运行：

| 实验 | 用户任务 | 外部内容 | 拟执行动作 | 多任务头 | 困难负样本 | 对抗增强 | 有限历史 |
|---|---:|---:|---:|---:|---:|---:|---:|
| E0 | 否 | 是 | 否 | 否 | 否 | 否 | 否 |
| E1 | 是 | 是 | 否 | 否 | 否 | 否 | 否 |
| E2 | 是 | 是 | 是 | 否 | 否 | 否 | 否 |
| E3 | 是 | 是 | 是 | 是 | 否 | 否 | 否 |
| E4 | 是 | 是 | 是 | 是 | 是 | 否 | 否 |
| E5（加分） | 是 | 是 | 是 | 是 | 是 | 是 | 否 |
| E6（加分） | 是 | 是 | 是 | 是 | 是 | 是 | 是 |

该表用于分别回答：

- 用户任务上下文是否有用；
- 动作信息是否有用；
- 目标一致性辅助任务是否有用；
- 困难负样本是否减少过度防御；
- 对抗增强是否改善未见变体而不显著增加误报；
- 有限历史是否改善渐进式目标偏移检测。

校准不作为提高分类准确率的普通消融，而作为独立后处理实验：比较未校准、Temperature Scaling 和保守固定阈值三种策略的 ECE、Brier、NLL、TPR@FPR 以及端到端决策差异。

可选实验：

- Small 与 Base 的性能/延迟比较；
- `max_length = 256 / 384 / 512`；
- 文档聚合策略；
- 类别加权交叉熵与 Focal Loss；
- 不同 `lambda`；
- 不同工具风险权重。

---

## 12. 本地与云端算力配置

### 12.1 本地电脑

当前电脑：

- 轻薄本；
- 32GB 内存；
- 无独立显卡。

适合完成：

- 数据下载、清洗、去重和统计；
- JSONL 转换；
- TF-IDF 和 Logistic Regression；
- 小规模 CPU 冒烟测试；
- 评测脚本和可视化；
- ONNX INT8 推理；
- FastAPI 和演示页面；
- 文档与 Git 管理。

不适合长时间完成：

- DeBERTa-base 完整微调；
- 大规模多随机种子实验；
- 大量 Agent LLM 推理。

### 12.2 推荐租用 GPU

### 首选：RTX 3090 24GB

- 性价比最高；
- 足够训练 DeBERTa-v3-base；
- 推荐用于多数训练和消融实验。

### 次选：RTX 4090 24GB

- 训练更快；
- 单价略高，但总费用可能接近 3090；
- 适合集中运行多个实验。

### 暂不建议

- V100：可以训练，但架构较旧；
- A100/A800/H800：本项目显存需求不高，通常不划算；
- 多卡：第一版没有必要，反而增加调试复杂度。

### 12.3 推荐云端软件环境

```text
Operating System: Ubuntu 22.04
Python: 3.10 或 3.11
PyTorch: 2.x
CUDA: 12.x（与镜像内 PyTorch 匹配）
Transformers: 固定具体版本
Datasets: 固定具体版本
scikit-learn
evaluate
accelerate
tensorboard
onnx
onnxruntime
fastapi
uvicorn
```

不要只写宽泛版本范围。第一次稳定训练后，应把确切版本写入 lock 文件或 requirements 文件。

### 12.4 租卡平台参考

- AutoDL：https://www.autodl.com/
- AutoDL GPU 与 CUDA 说明：https://www.autodl.com/docs/gpu/
- 阿里云 PAI DSW：https://help.aliyun.com/zh/pai/user-guide/dsw-overview
- Google Colab：https://research.google.com/colaboratory/

对国内个人项目而言，按小时计费的 RTX 3090/4090 通常更方便。云平台价格和库存会变化，启动实例前必须查看实时价格。

---

## 13. 算力时间与成本预算

以下以 2026-08-18 查询到的 AutoDL 展示价为参考：

- RTX 3090 24GB：约 1.32 元/小时；
- RTX 4090 24GB：约 1.88 元/小时。

价格来源：https://backup.autodl.com/

实际价格可能因地区、主机配置、会员、库存和活动变化。

### 13.1 预计 GPU 时间

| 工作 | GPU | 预计时长 | 预计费用 |
|---|---|---:|---:|
| Small 流水线验证 | 3090 | 1～2 小时 | 1.3～2.6 元 |
| 开源检测器统一推理基线 | 3090 | 2～5 小时 | 3～9 元 |
| 三种输入模型的初步实验 | 3090 | 3～6 小时 | 4～8 元 |
| Base 主模型训练 | 3090/4090 | 2～4 小时 | 3～8 元 |
| 困难负样本与多任务实验 | 3090/4090 | 4～8 小时 | 5～15 元 |
| 对抗增强训练与未见变体测试（可选） | 3090/4090 | 5～10 小时 | 7～19 元 |
| 核心消融实验 | 3090/4090 | 6～12 小时 | 8～23 元 |
| 最佳配置三个随机种子（时间允许时） | 3090/4090 | 8～15 小时 | 11～28 元 |
| 概率校准 | 本地 CPU/3090 | 1～2 小时 | 0～3 元 |
| 归因和有限多轮评测（可选） | 3090/4090 | 3～8 小时 | 4～15 元 |
| ONNX 导出前复测 | 3090 | 1～2 小时 | 1.3～2.6 元 |

### 13.2 推荐预算

```text
核心 C0～C3 GPU 预算：60～100 元
选择 1～2 个加分项后的 GPU 预算：100～180 元
GPU 失败重跑与扩展实验绝对上限：200 元
商业 LLM API：核心版 0 元；可选实验硬上限 50～100 元
整个项目推荐总预算：核心 60～100 元；扩展版不超过 280 元
```

核心闭环默认不调用商业 LLM API。AgentDojo、Task Shield 或 IPIGuard 的 API 实验属于可选加分项，只运行预先冻结的小型任务子集，所有请求与响应必须缓存；累计费用达到配置中的 50～100 元硬上限即停止，不允许临时追加预算掩盖复现问题。

Task Shield 严格复现优先核对论文使用的 `gpt-4o-2024-05-13`、提示词、AgentDojo 版本和任务配置。若模型不可用、环境无法对齐或达到预算上限，则采用下列降级顺序：

1. 只引用 `paper-reported` 结果；
2. 使用固定版本的本地开源小 LLM 验证流程；
3. 将结果明确标为 `Task-Shield-inspired approximation`；
4. 不把近似结果写成对原方法的严格复现或直接胜负比较。

### 13.3 节省费用规则

1. 所有代码先在本地用小数据跑通；
2. 云端第一次只跑 50 steps；
3. 确认日志和 checkpoint 正常后再全量训练；
4. 使用早停；
5. 下载或持久化最优 checkpoint；
6. 训练结束立即关闭实例；
7. 不在云端做慢速数据清洗；
8. 不为本项目租用 A100/H800；
9. 多随机种子只用于最终最佳配置；核心时间不足时先保证固定种子的完整复现；
10. 为每次训练设置最大步数或最大 epoch，防止脚本失控。

---

## 14. 云端训练操作流程

1. 本地完成代码和数据冒烟测试；
2. 提交 Git commit，记录当前版本；
3. 租用单张 RTX 3090 24GB；
4. 选择 PyTorch + CUDA 的 Ubuntu 镜像；
5. 把代码 clone 到云端；
6. 把清洗后的数据上传到持久化数据盘；
7. 安装固定版本依赖；
8. 运行环境检查并记录 `nvidia-smi` 和依赖版本；
9. 运行 50-step 云端冒烟测试；
10. 启动正式训练；
11. 监控显存、loss 和验证指标；
12. 训练结束后运行测试集评测；
13. 保存 checkpoint、配置、日志、预测结果和错误样本；
14. 下载关键文件到本地；
15. 验证本地能读取 checkpoint；
16. 关闭云端实例。

不得把 API 密钥写进仓库或训练配置。密钥应通过环境变量或云平台 Secret 功能提供。

---

## 15. 部署方案

### 15.1 模型导出

- 从最佳 PyTorch checkpoint 导出 ONNX；
- 验证 ONNX 与 PyTorch 预测差异；
- 进行 INT8 动态量化；
- 比较模型大小、延迟和指标变化；
- 保存 tokenizer 和标签映射。

### 15.2 推理接口

FastAPI 接口建议：

```http
POST /v1/evaluate
```

请求：

```json
{
  "user_goal": "Summarize this email.",
  "untrusted_content": "...",
  "proposed_action": "send_email(to='attacker@example.com', body=...) ",
  "tool_name": "send_email",
  "explain": false
}
```

响应：

```json
{
  "decision": "block",
  "risk_type": "data_exfiltration",
  "calibrated_risk_score": 0.97,
  "calibrated_alignment_score": 0.94,
  "tool_risk": 3,
  "reason": "The proposed external communication is inconsistent with the user's summarization goal."
}
```

`/v1/evaluate` 是核心实时路径，默认 `explain=false`，只返回校准分数、策略决定和模板化 `reason`，不运行 Integrated Gradients 或遮挡验证。解释功能作为可选的离线 notebook、异步任务或独立 `POST /v1/explain` 接口；只有该路径才返回 `evidence_spans` 和 token 归因。

### 15.3 本地演示

界面至少展示：

- 用户任务；
- 外部文档；
- 拟执行动作；
- 风险类别和分数；
- 最终 Allow / Confirm / Block 决策；
- 单文本模型与 IntentFence 预测对比；
- 正常样本和攻击样本快捷示例。

最终 ONNX INT8 模型应能在当前 32GB 内存轻薄本上进行 CPU 推理。

### 15.4 双门部署方式（可选加分）

```text
外部内容
   ↓
Gate A：快速内容检测
   ├── 高风险：隔离内容，不进入Agent上下文
   └── 低/中风险：附带风险元数据进入Agent
   ↓
Agent生成拟执行动作
   ↓
Gate B：任务-内容-历史-动作一致性检测
   ├── Allow
   ├── Confirm
   └── Block
   ↓
权限策略与真实工具
```

Gate A 可以使用 ProtectAI、PIGuard 或 IntentFence 单文本版本；Gate B 使用 IntentFence 完整模型。部署实验要比较复用同一模型与两个专用模型的安全性、内存和延迟。

### 15.5 Fail-open / Fail-closed 策略

检测服务故障、超时或返回无法解析结果时，根据动作风险处理：

| 动作类型 | 故障策略 | 说明 |
|---|---|---|
| 读取公开信息 | 受限 Fail-open | 可以继续读取，但禁止自动升级为高风险写操作 |
| 本地草稿和临时文件 | Confirm 或规则降级 | 保留操作记录 |
| 发邮件、上传、外部消息 | Fail-closed | 检测恢复或用户明确确认后执行 |
| 删除、支付、权限修改 | Fail-closed | 始终要求人工确认 |

服务必须提供 `/health`、模型版本、校准版本和策略版本。不能把“模型未响应”当成“低风险”。

### 15.6 延迟与可用性 SLO

第一版目标值，最终必须以当前轻薄本和云端机器实测修订：

- ONNX INT8 CPU 单请求 P50 ≤ 120ms；
- ONNX INT8 CPU 单请求 P95 ≤ 200ms；
- Gate A + Gate B 合计 P95 ≤ 400ms；
- API 可用性测试目标 ≥ 99.5%；
- 服务启动后先预热，再接收真实请求；
- 在线请求以低延迟为主，不为追求吞吐强制等待大 batch；
- 离线评测支持批处理；
- 超过超时阈值触发上节的分级故障策略。

这些是工程目标，不是现有结果。README 只能填写实测值，不能提前宣称已达到。

### 15.7 可解释性输出（离线或异步加分项）

若选择归因加分项，演示界面增加：

- 风险最高的外部文本 span；
- 用户目标、外部内容、动作三个区域的归因占比；
- 遮挡可疑 span 前后的风险变化；
- 模型判定与策略层最终决策的区别；
- 明确提示“归因用于辅助分析，不代表因果证明”。

归因默认关闭，不进入 `/v1/evaluate` 的 P50/P95 延迟统计。`/v1/explain` 单独报告耗时、Integrated Gradients 步数和遮挡次数，不能用实时接口 SLO 要求它。

### 15.8 漂移监控与迭代闭环（可选加分）

上线后不直接保存全部原始用户内容。优先记录脱敏统计：

- 输入长度、语言、工具类别分布；
- 校准风险分数和决策分布；
- Confirm、Block 和人工推翻比例；
- embedding 分布的漂移统计；
- 各风险类别的误报、漏报反馈；
- 模型、数据、校准和策略版本。

最小闭环：

1. 建立固定 Golden Regression Suite；
2. 新攻击样本先人工审核和去敏；
3. 每个候选模型必须通过历史攻击与正常任务回归；
4. 任一关键攻击类别明显回退则禁止发布；
5. 新增样本达到预设数量或出现明显分布漂移时再启动离线重训；
6. 重训模型先影子评估，不直接自动替换线上模型；
7. 支持回滚到上一个模型、校准器和策略版本。

第一版漂移监控只做离线报表和回归测试，不实现无人监管的在线学习。

---

## 16. 推荐项目目录结构

```text
IntentFence/
├── README.md
├── LICENSE
├── pyproject.toml
├── requirements.lock
├── configs/
│   ├── baseline.yaml
│   ├── deberta_small.yaml
│   ├── deberta_base.yaml
│   ├── augmentations.yaml
│   └── policy.yaml
├── data/
│   ├── raw/
│   ├── interim/
│   ├── processed/
│   └── DATASET_CARD.md
├── scripts/
│   ├── prepare_bipia.py
│   ├── prepare_injecagent.py
│   ├── prepare_notinject.py
│   ├── deduplicate.py
│   ├── audit_labels.py
│   └── build_splits.py
├── baselines/
│   ├── protectai.py
│   ├── piguard.py
│   ├── task_shield.md          # 可选：记录论文/复现/近似实现状态
│   └── run_all.py
├── src/intentfence/
│   ├── data.py
│   ├── modeling.py
│   ├── losses.py
│   ├── train.py
│   ├── evaluate.py
│   ├── calibration.py
│   ├── attribution.py          # 可选：离线/异步解释
│   ├── history.py              # 可选：最近 k 步历史拼接
│   ├── thresholds.py
│   └── policy.py
├── tests/
├── benchmarks/
│   ├── cross_dataset.py
│   ├── robustness.py
│   ├── overdefense.py
│   ├── calibration_eval.py
│   ├── latency.py
│   └── agentdojo_adapter.py
├── deployment/
│   ├── export_onnx.py
│   ├── api.py
│   ├── health.py
│   ├── monitoring.py           # 可选：离线漂移报告
│   └── Dockerfile              # 可选：生命周期工程
├── demo/
├── reports/
│   ├── figures/
│   ├── tables/
│   ├── data_quality/
│   ├── calibration/
│   ├── regression/
│   └── error_analysis/
├── checkpoints/
└── docs/
    ├── threat_model.md
    ├── model_card.md
    ├── baseline_protocol.md
    ├── reliability_policy.md
    └── experiment_log.md
```

大体积数据和 checkpoint 不应直接提交到 GitHub，应使用 `.gitignore`、Release、模型托管平台或外部存储。

---

## 17. 分阶段开发时间表

### 17.1 核心闭环：必须完成，6～8 周

核心闭环 C0～C3 是项目的唯一必交付路径。任何加分项都不能挤占数据质量、独立校准、跨数据集评测和 CPU 部署的时间。

### C0：定位与实验协议（第 1 周）

主要工作：

- 阅读 Task Shield、ProtectAI、PIGuard 和 AgentDojo 的核心设计；
- 明确 IntentFence 是轻量可训练的任务一致性检测器，而不是首次提出该思想；
- 冻结威胁模型、训练/验证/校准/测试边界、主指标和公平比较规则；
- 创建项目骨架、配置系统和实验日志模板；
- 核心流程设为零商业 API；为可选 API 实验设置 50～100 元硬上限；
- 记录 Task Shield 的 `paper-reported / reproduced / inspired approximation` 三种结果标签。

阶段出口：

- `docs/baseline_protocol.md` 完成；
- 测试集、校准集与训练集边界明确；
- 不再依赖训练结果临时修改主指标。

### C1：数据质量与必要基线（第 2～3 周）

第 2 周：

- 下载并转换 BIPIA、InjecAgent、NotInject；
- 定义统一 JSONL schema；
- 完成去重、模板分组和固定的 train/validation/calibration/test split；
- 分层人工审计至少 200 条样本；
- 输出标签质量报告。

第 3 周：

- 实现规则和 TF-IDF 基线；
- 运行 ProtectAI 和 PIGuard/InjecGuard 两个核心开源基线；
- 测量统一数据上的 Accuracy、F1、TPR@1%FPR、误报和延迟；
- 建立统一预测文件格式和错误分析脚本。

阶段出口：

- 标签质量报告完成；
- 开源检测器基线表完成；
- 训练/校准/测试数据无明显泄漏；
- 未完成上述条件前不启动 Base 正式训练。

### C2：核心模型与校准（第 4～6 周）

第 4～5 周：

- 本地完成 CPU 冒烟测试；
- 训练 Small 单文本、上下文和动作感知模型；
- 实现双任务输出头；
- 验证上下文和动作信息是否真正带来增益。

第 5～6 周：

- 训练 Base 主模型；
- 加入困难负样本；
- 完成小范围超参数选择；
- 拟合 Temperature Scaling；
- 冻结低误报阈值和 Allow/Confirm/Block 策略；
- 完成核心输入消融与困难负样本实验；
- 在 BIPIA 未见模板、InjecAgent 和 NotInject 上完成最终评测。

阶段出口：

- 完整模型相对同骨干单文本模型有可解释的增益，或明确得到负结果；
- 完成校准报告；
- 能在 InjecAgent 上进行独立跨数据集评测；
- 如果没有上下文/动作增益，先分析数据和任务定义，不进入复杂扩展。

### C3：部署与项目包装（第 7～8 周）

- 最佳配置至少完成固定种子复现；时间允许时再运行三个随机种子；
- 导出 ONNX 并进行 INT8 量化；
- 完成本机 SLO 基准测试；
- 完成模型、校准器和策略配置版本化；
- 完成 FastAPI 和本地演示界面；
- 完成 README、模型卡、威胁模型、数据卡和实验报告；
- 整理真实指标的简历描述和演示视频。

阶段出口：

- 从数据处理到部署可以按 README 复现；
- 普通 CPU 可以运行量化模型；
- 简历中的所有数字都能由仓库结果文件追溯。

### 17.2 可选加分阶段：核心完成后选择 1～2 项

#### B1：对抗训练与鲁棒性（推荐优先）

- 受控生成大小写、空白、后置指令、格式包装等训练增强；
- 将训练增强族和最终未见变换族严格隔离；
- 同时报 TPR@1% FPR、NotInject FPR 和正常效用变化；
- 只有安全收益没有以明显误报上升为代价时才保留。

预计新增 1～2 周。

#### B2：Gate A + Gate B 与 AgentDojo（推荐优先）

- 实现外部内容入口检测和动作执行前检测；
- 在固定 AgentDojo 版本与任务子集上比较无防御、文本检测器和 IntentFence；
- 使用官方 task utility 检查器报告 Benign Utility、Utility Under Attack 和 Targeted ASR；
- Task Shield 只按已声明的三种复现标签之一呈现；
- 完成 Fail-open/Fail-closed 和高风险工具确认策略。

预计新增 2～3 周，可能产生商业 API 费用。

#### B3：有限历史

- 只比较当前步输入与最近 `k=3` 步历史拼接；
- 不新增 `d_t`、累计风险公式或时序模型；
- 只有简单历史拼接显著有效时，才另立后续研究。

预计新增约 1 周。

#### B4：离线归因

- 在 Confirm/Block 和错误案例上运行 Integrated Gradients；
- 提供独立 `/v1/explain` 或离线 notebook；
- 用遮挡实验检查高亮 span 的稳定性；
- 不计入 `/v1/evaluate` 的实时 SLO。

预计新增约 1 周。

#### B5：生命周期工程

- Golden Regression Suite；
- 离线漂移报告和版本回退说明；
- Dockerfile 与发布检查清单。

预计新增 1～2 周。

标准承诺只覆盖 C0～C3，共 6～8 周。如果只能利用业余时间，可扩展为 8～10 周。选择两个推荐加分项后的合理总周期约 10～13 周；全部实现 B1～B5 应按 12～16 周以上规划，而不是继续承诺 8 周完成。

---

## 18. 验收标准

### 核心完成线（简历可用版本）

- 完成统一数据格式；
- 完成基础标签质量抽样审计；
- 完成 TF-IDF 基线；
- 运行 ProtectAI 与 PIGuard/InjecGuard 两个开源检测器基线；
- 完成 DeBERTa-small 流水线和 DeBERTa-base 动作感知主模型；
- 完成单文本、上下文和动作感知输入消融；
- 在模板隔离测试集、InjecAgent 跨数据集和 NotInject 误报集上评测；
- 明确训练集、校准集和测试集；
- 完成 Temperature Scaling、ECE/Brier/NLL 和阈值冻结；
- 导出 ONNX INT8 并报告安全指标量化前后变化；
- 提供 FastAPI 推理接口；
- 在本机 CPU 上报告 P50/P95 延迟；
- 提供可复现 README、模型卡和实验表格。

### 加分版本（选择 1～2 组，不要求全部完成）

- 鲁棒组：对抗训练、未见变换和误报代价分析；
- 系统组：Gate A + Gate B、AgentDojo 官方 Utility/ASR、故障策略；
- 多轮组：最近 3 步历史拼接与单步模型对比；
- 解释组：离线 Integrated Gradients、span 高亮与遮挡验证；
- 生命周期组：Golden Regression、漂移报告、Docker 和回滚说明。

### 优秀版本

- 在一个选定加分方向上形成完整、可复现的研究结论；
- 加入工具风险等级；
- 如选择多轮，只加入最近 3 步历史，不虚构未经验证的累计风险公式；
- 支持中英文和 Unicode 攻击；
- 提交一个公开模型或数据处理工具；
- 向 BIPIA、InjecAgent、AgentDojo 或相关开源项目贡献适配代码或修复。

---

## 19. 项目风险与应对

| 风险 | 表现 | 应对方式 |
|---|---|---|
| 数据泄漏 | 测试指标异常高 | 按模板分组、近重复检测、跨数据集测试 |
| 标签噪声 | 高损失样本和指标异常 | 分层人工审计、模糊集、标签版本记录 |
| 类别不平衡 | 少数攻击召回率低 | 类别权重、分层采样、逐类报告 |
| 关键词捷径 | 敏感词一出现就拦截 | 困难负样本、NotInject、错误分析 |
| 与 Task Shield 思想重合 | 创新主张站不住 | 定位为轻量、可校准、低成本近似并公平对比 |
| 未校准分数 | 风险阈值不可解释 | 独立校准集、Temperature Scaling、ECE/Brier/NLL |
| 对抗增强过拟合 | 已见变体很好、未知攻击仍失败 | 训练与测试变换族隔离 |
| 长文档截断 | 攻击位于文档尾部时漏检 | 滑动窗口和文档级聚合 |
| 云端费用失控 | 忘记关机或反复调试 | 本地冒烟测试、早停、预算上限 |
| 指标不可复现 | 每次训练差异较大 | 固定 split、版本、seed，运行三次 |
| 模型延迟高 | CPU 演示卡顿 | ONNX、INT8、Small/Base 对比 |
| 检测器故障 | 高风险动作绕过检查 | 分级 Fail-closed、健康检查、超时与降级策略 |
| 线上分布漂移 | 新攻击性能退化 | Golden Suite、漂移报告、人工审核后离线重训 |
| 防御影响正常任务 | Agent 大量拒绝执行 | TPR@固定FPR、工具分级、人工确认 |
| 研究范围过大 | 长期无法完成 | 第一版只做英文文本和固定工具动作 |
| Task Shield 无法复现 | API、模型或环境版本不可用 | 区分论文报告、严格复现和本地近似；不把它作为核心完成条件 |
| 商业 API 费用失控 | AgentDojo/LLM 裁判反复调用 | 核心零 API、请求缓存、固定子集、50～100 元硬上限 |
| 指标互相冲突 | 为速度牺牲安全或为召回牺牲效用 | 先冻结 FPR/Utility 硬约束，再优化安全指标，工程指标最后决策 |

---

## 20. 安全、伦理与负责任使用

- 只使用公开数据集、自己拥有的系统或明确授权的测试环境；
- 不向第三方在线 Agent、RAG 或企业系统发送攻击测试；
- 不在仓库中发布真实凭据、个人数据或可识别隐私信息；
- 对攻击样本的发布遵守原始数据集许可证和使用条件；
- 演示工具调用必须使用 mock 工具或沙箱，不能真的发送邮件、上传文件、删除数据或支付；
- README 应明确说明模型可能被自适应攻击绕过；
- 高风险动作始终保留权限控制和人工确认；
- 模型用于安全研究和防御评估，不应被描述为绝对安全保证。

---

## 21. 简历展示重点

完成后应突出以下能力：

- 在 Task Shield 类任务一致性思想基础上，实现轻量、可监督训练、可校准的动作感知安全分类器；
- 从基础 DeBERTa 权重完成多任务微调；
- 构建公开检测器基线、模板隔离、跨数据集和低误报率安全评测；
- 完成 Temperature Scaling、校准误差和工具风险分级；
- 如果选择鲁棒加分项：通过受控对抗增强提升鲁棒性，并严格保留未见攻击变体；
- 如果选择系统加分项：按 AgentDojo 官方协议验证 Targeted ASR、Benign Utility 与 Utility Under Attack；
- 如果选择双门加分项：实现入口内容检测与动作执行前一致性检测，并定义故障策略；
- 将 PyTorch 模型导出并量化为可在普通 CPU 部署的 ONNX 服务；
- 建立完整的数据、训练、校准、评测、API 和模型卡流程；Docker、归因和漂移监控只在实际完成后写入简历。

简历中的指标必须使用最终真实实验结果填写，不能提前虚构。

---

## 22. 下一步立即执行清单

1. 在 `E:\IntentFence` 中初始化 Git 仓库；
2. 创建第 16 节的目录骨架；
3. 编写 `docs/baseline_protocol.md`，冻结基线、指标和比较规则；
4. 建立 Python 虚拟环境并固定基础依赖；
5. 下载并检查 BIPIA、InjecAgent、NotInject 数据结构；
6. 定义统一 JSONL schema 和标签规范；
7. 转换 100 条样本作为最小数据集；
8. 进行第一轮标签人工审计；
9. 实现 TF-IDF + Logistic Regression；
10. 运行 ProtectAI 基线并统一输出格式；
11. 建立训练、校准、测试的隔离 split；
12. 完成 CPU 冒烟测试后再首次租用 GPU。

---

## 23. 最终决策摘要

- 项目方向：轻量、可校准、动作感知的间接提示注入安全闸门；
- 创新定位：不是首次提出任务一致性，而是低成本、可训练、可部署地近似并扩展 Task Shield 类检查；
- 交付原则：先保 C0～C3 核心闭环，加分项根据时间与预算最多选择 1～2 项；
- 主模型：DeBERTa-v3-base；
- 验证模型：DeBERTa-v3-small；
- 训练方式：普通基础权重上的监督微调与多任务学习；
- 核心基线：TF-IDF、同骨干单文本模型、ProtectAI、PIGuard/InjecGuard；
- 可选系统参考：Task Shield，必须标注为论文报告、严格复现或 inspired approximation；
- 核心模型：Gate B 动作执行前一致性检测；Gate A + Gate B 属于系统加分项；
- 核心增强：困难负样本与 Temperature Scaling；对抗训练、有限历史和归因属于加分项；
- 数据划分：从训练来源池按组预留 10%～15% 独立 calibration split；
- 输入格式：默认 `[SEP]` 分隔；新增特殊 token 只做消融；
- 推荐 GPU：单张 RTX 3090 24GB；
- 核心 GPU 预算：60～100 元；加分版 GPU 预算：100～180 元；API 可选硬上限：50～100 元；
- 本地部署：ONNX INT8 + FastAPI；
- 标准周期：核心 6～8 周；选择两个加分项约 10～13 周；全量扩展至少 12～16 周；
- 指标优先级：FPR/Utility 硬约束 → TPR@1%FPR 或 Targeted ASR → 校准诊断 → 延迟与成本；
- AgentDojo：只使用官方任务检查器计算 Benign Utility 和 Utility Under Attack；
- 归因路径：Integrated Gradients 仅离线或异步运行，不进入 `/v1/evaluate` 实时 SLO；
- 发布要求：核心版通过标签质量审计、独立校准、跨数据集测试和 CPU 实测后即可作为简历项目发布。

---

## 24. 关键参考与复现入口

- Task Shield（ACL 2025）：https://aclanthology.org/2025.acl-long.1435/
- ProtectAI Prompt Injection v2：https://huggingface.co/protectai/deberta-v3-base-prompt-injection-v2
- ProtectAI LLM Guard：https://github.com/protectai/llm-guard
- PIGuard / InjecGuard：https://github.com/safolab-wisc/injecguard
- Microsoft BIPIA：https://github.com/microsoft/BIPIA
- InjecAgent：https://github.com/uiuc-kang-lab/InjecAgent
- AgentDojo：https://github.com/ethz-spylab/agentdojo
- AgentDojo 任务与效用协议：https://agentdojo.spylab.ai/concepts/task_suite_and_tasks/
- AgentDojo BaseUserTask API：https://agentdojo.spylab.ai/api/base_tasks/
- IPIGuard：https://github.com/Greysahy/ipiguard
- MultiTurnAgentAttack：https://github.com/amazon-science/MultiTurnAgentAttack
- On Calibration of Modern Neural Networks：https://arxiv.org/abs/1706.04599
- DeBERTa-v3-base 配置：https://huggingface.co/microsoft/deberta-v3-base/blob/main/config.json
- Integrated Gradients 使用参考：https://github.com/ankurtaly/Integrated-Gradients

引用现有结果时必须核对其数据、模型、阈值、攻击设置和指标定义，不直接把不同论文中的数字横向拼接成排名。
