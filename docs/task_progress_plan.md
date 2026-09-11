# IntentFence 任务推进与实验计划

## Material Passport

- Origin Skill: academic-research-suite / experiment-agent
- Origin Mode: plan
- Origin Date: 2026-08-20
- Verification Status: UNVERIFIED
- Version Label: code_plan_v1
- Project Goal: 论文级实验质量，最终用于公开 GitHub 与简历展示

## 1. 推进规则

本项目按阶段推进。用户于2026-09-11明确授权：“确认，之后都改成你自己推进，不需要我确认”。**数据与工程阶段完成后汇报并自主继续，不再等待逐阶段确认**。历史章节中的阶段暂停语句保留为当时记录，由此最新授权覆盖。每阶段汇报：

1. 本阶段完成了什么；
2. 修改或生成了哪些文件；
3. 执行了哪些测试，哪些通过或失败；
4. 尚存风险和未完成事项；
5. 下一阶段计划与预计资源；
6. 继续下一项必要的数据或工程工作，吸收用户随时提供的调整。

常规阶段转换已有持续授权，不重复请求确认。模型训练仍按 AGENTS.md 由项目所有者执行，独立人审不能由 AI 代替；租用 GPU、付费 API、新来源条款等具体资源或责任边界仍依执行策略处理。

从 2026-08-24 起，每个阶段在通过该阶段的静态、合成或用户执行验证后，还必须：

1. 只提交代码、配置、测试和允许公开的文档，不提交 raw/interim/processed 数据、JSON/CSV 质量报告、模型权重、凭据或缓存；
2. 在独立功能分支创建阶段提交并显式推送到远程同名分支，不使用可能误推 `main` 的裸 `git push`；
3. 在阶段汇报中记录远程分支、提交 SHA、验证结果和研究证据状态。

用户已于 2026-08-24 更新执行授权：Codex 可以连续执行 C1 真实数据下载、转换、合并、去重、划分、标签审核抽样/预审和训练前报告，并更新文档、完成阶段提交；`human_verified=true` 仍需项目所有者完成独立人类确认。后续每轮训练前，Codex 必须展示完整命令并等待项目所有者对该轮命令明确确认；确认后可执行已批准的训练命令。该授权不解除校准或最终测试锁。

用户已于 2026-08-28 冻结后续模型训练的执行形式：所有会更新学习参数的工程或正式科研运行，
必须在启动前具有版本化配置和可审查的 PowerShell/Bash/Slurm 启动脚本；不得把临时手敲、未记录
参数的命令作为正式实验。启动脚本至少应执行数据/环境预检、拒绝覆盖既有输出、记录起止时间与
实际依赖/硬件、调用固定训练入口、验证 checkpoint，并生成绑定 Git commit、配置、数据哈希、
seed、成本和产物哈希的 run manifest。每个变体和 seed 使用独立输出目录；失败不得静默重试。
每轮命令审查确认后，Codex 可以执行训练脚本；没有该轮确认不得启动。Codex 不得修改最终测试、校准参数或冻结协议字段。

## 2. 状态定义

| 标记 | 含义 |
|---|---|
| ✅ 已实现并验证 | 代码已存在，并通过当前阶段要求的测试 |
| 🟡 已实现，待真实验证 | 代码或文档存在，只在单元测试/合成数据验证，不能支持论文结论 |
| 🔵 进行中 | 当前阶段正在执行 |
| ⬜ 未开始 | 尚未实现或执行 |
| ⛔ 等待资源/确认 | 需要用户确认、GPU、外部数据或付费资源 |

状态必须分别描述“工程实现”和“研究证据”。例如，训练代码写完不等于模型训练完成；ONNX 导出脚本写完不等于完成量化安全评测。

## 3. 冻结的研究目标

### 3.1 总目标

研究一个轻量、可监督训练、可独立校准、动作感知的间接提示注入检测器，判断它能否在低误报约束下，以低于在线 LLM 裁判的推理成本实现有竞争力的安全性和正常任务效用。

### 3.2 核心研究问题

| ID | 研究问题 | 主要比较 | 主要指标 |
|---|---|---|---|
| H1 | 用户任务上下文能否降低误报？ | 单文本 A vs 上下文 B | TPR@1% FPR、NotInject FPR |
| H2 | 拟执行动作能否提高攻击识别？ | 上下文 B vs 动作模型 C | TPR@1% FPR、逐类 Recall |
| H3 | 困难负样本能否改善泛化？ | 无困难负样本 vs 加入困难负样本 | NotInject FPR、攻击 TPR |
| H4 | 多任务头是否有独立收益？ | 仅 Risk Head vs Risk + Alignment | 跨数据集 TPR、Macro-F1 |
| H5 | 独立校准是否支持稳定分级？ | 校准前 vs Temperature Scaling | ECE、Brier、NLL、阈值稳定性 |
| H6（可选） | 轻量模型是否有系统成本优势？ | IntentFence vs LLM 一致性裁判 | 安全/效用、P95、成本 |

H1～H5 属于核心论文级实验。H6 只有在核心实验完成且用户批准付费/API或本地 LLM 实验后执行。

## 4. 总体阶段路线

| 阶段 | 目标 | 主要工具/方法 | 当前工程状态 | 当前研究证据 | 阶段出口 |
|---|---|---|---|---|---|
| P0 | 冻结推进计划与协作规则 | Markdown、Git 状态审查 | ✅ | 不适用 | 用户确认本计划 |
| C0 | 冻结研究协议与文献定位 | 论文原文、官方文档、实验注册表 | ✅ 已冻结 | ✅ 文献证据已核验；实验结果尚未产生 | 用户已批准协议 1.0.0 |
| C1 | 数据质量与必要基线框架 | 严格适配器、manifest、审计、泄漏检查、基线接口 | ✅ 框架与真实执行闭环完成 | ✅ 证据 validated；⛔ 训练就绪失败 | 真实 manifest、审核和报告已生成；按训练入口决策补数据/修订协议前停止 |
| C1B | Route B 训练前数据扩充（双 AI 工程路线） | 五分类训练来源、独立 Alignment、动作构造与双 AI 审核、v2 manifest | ✅ 双 AI 包、metadata 与分析器完成 | ⛔ 两次 AI B 运行均未通过预注册质量门；已接受为工程负结果 | 负结果已记录；正式训练与最终测试继续锁定 |
| C2a | Small 模型流水线与输入消融 | PyTorch、Transformers、DeBERTa-v3-small | 🟡 | ⬜ | CPU 冒烟通过，A/B/C 可重复训练和加载 |
| C2b | Base 主实验与困难负样本 | 云 GPU、DeBERTa-v3-base、3 seeds | 🟡 | ⛔ | H1～H4 主实验完成，结果可追溯 |
| C2c | 独立校准与阈值冻结 | Temperature Scaling、校准集 | 🟡 | ⬜ | H5 完成，温度和阈值冻结 |
| C3a | 跨数据集与过度防御评测 | Test A/B/C、Bootstrap CI、错误分析 | 🟡 | ⬜ | 最终测试只执行一次，报告完成 |
| C3b | ONNX INT8 与 CPU 部署 | ONNX Runtime、FastAPI、延迟基准 | 🟡 | ⬜ | 量化前后安全与 P50/P95 实测完成 |
| C4 | 论文式报告与简历包装 | 报告、模型卡、数据卡、演示 | 🟡 | ⬜ | 所有公开数字可由结果文件追溯 |
| G1 | 完善并发布 GitHub Release | Git、GitHub、CI、Release | 🟡 | 不适用 | `Jvn1vs/IntentFence` 公开可访问、CI 通过且材料完整 |
| B1/B2 | 最多选择 1～2 个加分项 | 鲁棒增强、AgentDojo 双门系统 | ⬜ | ⬜ | 核心完成后另行批准 |

## 5. 分阶段任务、工具与测试

### P0：计划冻结（已完成）

#### 要做什么

- 将论文级目标和简历交付目标统一到同一条核心路线；
- 定义阶段门、状态语义、汇报格式和停止点；
- 记录 GPU、数据下载和 GitHub 发布条件；
- 对已有工程代码进行诚实状态标注。

#### 用什么做

- `docs/task_progress_plan.md`：唯一任务进度主文档；
- Git：P0 当时只查看状态；从 2026-08-24 起按第 1 节的新阶段检查点规则提交并推送后续阶段；
- Academic Research Suite experiment plan：约束实验可验证性和状态声明。

#### 当前状态

- ✅ 本计划已创建；
- ✅ 用户已确认目标为论文级实验，最终用于简历；
- ✅ 用户允许下载公开数据，允许后续租用 GPU；
- ✅ GitHub 目标确定为公开 `Jvn1vs/IntentFence`；
- ✅ GitHub 远程仓库 `Jvn1vs/IntentFence` 已存在；阶段成果先推送独立功能分支，正式合并或 Release 仍需单独批准。

#### 要测试什么

- 文档是否同时包含任务、工具、状态、测试和出口条件；
- 每个阶段是否有明确停止点；
- 是否区分工程实现与研究证据；
- 是否存在提前宣称模型指标或论文结论的内容。

#### 出口条件

- 用户审阅并确认本计划后，才进入 C0。

---

### C0：研究协议与文献定位冻结

#### 要做什么

- 核对 Task Shield、BIPIA、InjecAgent、InjecGuard/NotInject、AgentDojo、ProtectAI 的论文、仓库、许可证和版本；
- 建立相关工作矩阵，明确 IntentFence 与现有任务一致性防御的差异；
- 冻结 H1～H5、输入 A/B/C、主指标和失败判据；
- 冻结 train/validation/calibration/test A～D 的用途；
- 冻结随机种子、模型选择规则、阈值规则、硬件/预算记录格式；
- 建立实验注册表，最终测试结果出现后不得修改主假设或指标。

#### 用什么做

- 论文原文、官方 GitHub/模型卡/官方文档；
- `docs/baseline_protocol.md`、`docs/threat_model.md`、`docs/experiment_log.md`；
- Markdown 文献矩阵与实验注册 JSON/YAML；
- Git commit 与文件 SHA-256 追踪协议版本。

#### 当前状态

- ✅ 已用论文原文、官方仓库、模型卡和数据卡完成核心来源核验；
- ✅ 已建立相关工作矩阵，并明确 Task Shield 是最接近的概念先例；
- ✅ 已生成 H1～H5、A/B/C、互斥数据角色、三随机种子、模型选择、校准阈值、统计和失败判据的预注册候选；
- ✅ 已建立机器可读实验注册表、上游 revision/许可证清单和 SHA-256 冻结候选；
- ✅ 已记录外部模型污染风险、NotInject 小样本限制和非商业许可证隔离规则；
- ✅ 用户已于 2026-08-20 批准冻结，协议状态为 `frozen`，并已另行批准开展 C1 框架工作。
- ✅ 用户明确由自己执行所有真实模型训练；Codex 可执行 C1 数据流程、搭建和验证框架，并分析训练日志。

#### 要测试什么

- 每个研究问题是否对应唯一主要比较和主要指标；
- 验证集、校准集和最终测试是否角色互斥；
- 外部基线是否记录潜在训练数据污染；
- Task Shield 结果是否严格标记为 `paper-reported`、`reproduced` 或 `Task-Shield-inspired approximation`；
- 是否提前定义负结果处理方式；
- 所有引用、版本和技术事实是否来自可核验的一手来源。

#### 出口条件

- 用户批准冻结后的研究协议；
- C0 文档检查全部通过；
- 在 C1 开始后，最终测试指标与边界不再随结果修改。

---

### C1：数据获取、审计、隔离划分与基线

#### 要做什么

1. 下载 BIPIA、InjecAgent、InjecGuard/NotInject，并记录 commit、许可证和文件哈希；
2. 检查真实字段结构，修正各数据适配器；
3. 转换为统一 JSONL schema；
4. 精确去重、近重复检测、模板分组；
5. 分层人工审计至少 200 条；
6. 输出 Risk × Alignment 列联表、条件概率和互信息；
7. 建立互斥 train/validation/calibration/test split；
8. 完成规则、word TF-IDF、char TF-IDF、ProtectAI、PIGuard/InjecGuard 的可重复运行框架和合成 smoke；正式 Test A/B/C 基线与冻结模型一起留到 C3 单次评测；
9. 生成数据卡、标签质量报告和训练就绪/阻塞报告；正式基线表在 C3 由同一批冻结预测统一生成。

#### 用什么做

- `scripts/download_sources.py`、`prepare_*.py`、`deduplicate.py`、`build_splits.py`、`audit_labels.py`；
- Pydantic、scikit-learn、字符 n-gram/Jaccard；
- 规则检测器、TF-IDF + Logistic Regression；
- Hugging Face Transformers 运行冻结 revision 的外部检测器；
- CSV/JSON/Markdown 报告。

#### 当前状态

- ✅ 固定 revision 下载器已实现，默认只预览；项目所有者确认来源条款后，Codex 或项目所有者可显式下载；多来源中断后可用 `--resume` 验证并复用已有来源、补齐缺失来源和原子生成完整 manifest；
- ✅ BIPIA、InjecAgent、NotInject 严格字段 profile 已实现并通过合成 fixture 测试，不再猜测字段或标签；
- ✅ 每行记录 adapter、label、action provenance；BIPIA 缺失动作、InjecAgent 基准目标动作和 NotInject 协议包装被明确隔离；
- ✅ 转换报告记录输入/输出 SHA-256、跳过数、标签与动作 provenance；严格模式 `skipped` 必须为 0；
- ✅ 人工审计抽样、审计汇总、修订应用、模糊样本排除框架已实现；抽样 seed、算法、分层字段和不可编辑行摘要均可从 canonical 输入重放验证；
- ✅ 精确/近重复、模板组跨 split、动作缺失检查和最终 split manifest 自哈希已实现；训练前报告会重放转换、merge、审计应用、去重和固定 seed 划分，而不是只相信 sidecar 声明；
- ✅ 规则、TF-IDF、ProtectAI、PIGuard 的统一连续分数接口、calibration/test backend+revision 绑定、calibration-only 阈值评估和完整矩阵聚合框架已实现；真实最终测试基线不会在模型冻结前提前运行；
- ✅ 执行权已更新：Codex 可运行 C1 真实数据处理、标签审核抽样和 AI 预审；只有项目所有者独立确认后才能设置 `human_verified=true`。学习基线拟合、模型/校准参数更新与所有训练仍只由项目所有者执行；
- ✅ 用户已完成 Conda `intentfence` 环境准备：Python 3.12.13；`pip check` 无损坏依赖；`huggingface_hub`、`jsonlines`、`nltk`、`pandas`、`pyarrow`、`transformers`、`yaml` 和项目包导入通过；固定 BIPIA email builder 导入预检通过；
- ✅ 用户已完成 BIPIA、InjecAgent、NotInject 固定来源预览；URL、revision、许可证发现和目标路径与冻结注册表一致，预览后 Git 工作区干净；
- ✅ 用户已使用 `--resume` 完成 BIPIA、InjecAgent 与 NotInject 固定来源下载；`source_manifest.json` 的 3 个 revision 与冻结注册表一致，131 个登记文件的存在性、大小和实际 SHA-256 已逐项复核且错误为 0；
- ✅ 已用 `intentfence` Conda 解释器完成 BIPIA email builder 无副作用预览；冻结 revision、train context/attack 路径和计划输出路径均正确，未生成数据文件；
- ✅ C1 手册命令已统一为从 Conda 环境登记表唯一解析解释器并 fail-fast；BIPIA builder 最小依赖已纳入 `data` extra；正式 split build 必须恰好生成六角色，manifest 会绑定每个角色的路径、行数和 SHA-256；动作校验按 split/source/provenance 白名单 fail-closed，Test B/C 的代理证据不会被误称为 observed action；
- ✅ 训练前报告生成器已实现：在用户完成第 7 节后会复核全部来源/转换/审计/manifest 证据，并生成 train-only Risk × Alignment 列联/条件概率/互信息、类别覆盖、动作就绪状态、标签质量报告和数据卡；
- 🟡 项目所有者已完成第 3 节的 email attack export、generated 严格转换和 clean 严格转换；转换报告分别记录 11,250 条攻击样本和 50 条 clean 样本，均为 `skipped=0`，报告中的输入/输出 SHA-256 已与现存文件复核一致。由于 export 产生在 builder sidecar 功能加入前，第 8 节前还须由项目所有者用 `--verify-existing` 重建到临时文件并生成 `reproduced_verified` 报告，现有数据无需覆盖；
- ✅ 项目所有者已完成第 4 节 InjecAgent 转换：direct-harm 报告记录 510 条，data-stealing 报告记录 544 条；两者均为 `skipped=0`、`split=test_b`、`action_provenance=benchmark_target`，且各自输入/输出 SHA-256 与现存文件一致；
- ⛔ BIPIA 不提供拟执行动作，且当前尚无已批准的动作构造与独立审计流程；第 3～8 节只能关闭 A/B 数据证据路线并生成训练前报告，模型 C 数据门仍阻塞，不得伪造动作；
- ⛔ 当前 BIPIA 构造只直接提供 `benign` 与 `instruction_hijacking`，且 schema 令 Alignment 成为 Risk 的确定性二值映射；正式训练前必须依据真实报告，由项目所有者决定是修订为二元 risk-only 主目标，还是增加经许可/审计的训练类与独立 Alignment 标注。冻结协议尚未被擅自修改；
- ✅ 已新增 `docs/training_entry_decision.md`，把二元 risk-only、保留五分类扩充数据、仅 A/B 工程冒烟三条路线及其证据/批准边界写清；当前状态仍为项目所有者待决，不构成协议修改；
- ✅ 第 5 节三个 NotInject 子集已完成：one/two/three 各 113 条，共 339 条；均为 `skipped=0`、`split=test_c`、`risk_label=benign`、`action_provenance=protocol_wrapper`，三份输入/输出 SHA-256 与报告一致，canonical schema 通过且跨子集重复 `sample_id=0`；
- ✅ 第 6 节 BIPIA 训练池合并完成：11,300 条（50 `benign`、11,250 `instruction_hijacking`），输出 SHA-256 `3fc10575e89e2304e2894629489a876b8e7c935a87e1aaea627be57386be725a`；固定 seed=42 的审核表抽取 200 条（50 clean、150 attack）；
- ✅ 项目所有者已检查全部 200 条 AI 预审建议并确认均为 `correct`；正式审核汇总 `status=passed`、`reviewer=project_owner`，应用只改变 200 行的 `human_verified`，11,100 条未抽样记录保留。正式审核 CSV SHA-256 为 `2e2990f0a62af8a163bae66e857debd8203d5a16f37e20f2f58c8abe2a717624`，审核后训练池 SHA-256 为 `1fd5559c18dd358a0e0184154af2e4a859cd0f5d13caff4f07f0b9125e397a99`；
- ✅ 第 7 节完成：BIPIA 11,300 条经 163 个精确重复对和 8,450 个近重复对去重后保留 2,687 条；加 Test B/C 后六角色共 4,080 条。manifest 文件 SHA-256 `e04a16f4b23b9811dc68c4a98cc6fe4152da582d90c0fbbfd6eb225efae1b545`、封存自哈希 `bdd9fe80de528083591652bc743d878777adb55bb082bf4d5df6fc5f7d1f0063`；context/external-action 完整性报告均 passed，模板组和近重复跨 split 泄漏为 0；
- ✅ 第 8 节完成：BIPIA builder 为 `reproduced_verified`；训练前报告重放整条证据链并给出 `evidence_status=validated`、总计 4,080 条。统计 JSON SHA-256 `f9008ff67c7f307ae2544695091625a861f22d78950238802c08946cf4f4f81f`，允许公开的标签报告与数据卡已生成；
- ⛔ 训练就绪失败：train 为 39 benign/1,176 instruction_hijacking，但 validation 493、calibration 493、test_a 486 均没有 benign；train 缺少 data_exfiltration/privilege_escalation/tool_manipulation；Alignment 为 Risk 的确定性映射；Model C 的四个内部角色都缺少获批 action。`formal_training_authorized=false`，真实 Test A/B/C 基线仍受单次测试锁保护；
- ✅ C1 工程框架与真实数据执行出口均已完成并形成 validated 证据；⛔ 研究训练出口因类别覆盖、Alignment 独立性和 action provenance 不足而关闭，不能进入真实训练结论阶段。

#### 要测试什么

- Schema：必填字段、标签映射、严重度、重复 `sample_id`；
- Adapter：每个来源至少建立固定 fixture 与字段映射测试；
- 去重：精确重复、近重复阈值、误删人工抽样；
- Split：任何 `template_group`/来源簇不得跨 split；
- 校准集：每类数量与正负比例，少数类不足标为 `insufficient evidence`；
- 审计：正确/错误/模糊比例，第二标注者或间隔盲审一致性；
- 基线：统一预测格式、默认阈值、1% FPR 阈值、P50/P95、异常样本；
- 数据污染：记录外部模型可能见过的数据，不虚假声称完成其训练成员去重。

#### 出口条件

- 工程出口：C1 框架校验、单元测试、lint、构建和用户手册通过；
- C1 数据执行出口：按 `docs/c1_user_runbook.md` 生成并复核以下证据；
- 标签质量报告完成；
- 所有 split 无模板/近重复泄漏；
- 本地和外部必要基线的接口、固定 revision 和合成 smoke 可重复；真实 Test A/B/C 基线结果按 test lock 延后到 C3 单次正式评测；
- 数据版本、哈希、许可证和结果均可追溯；
- 未达到出口条件不得租 GPU 训练 Base。

---

### C1B：Route B 五分类、独立 Alignment 与动作数据扩充（当前为双 AI 工程路线）

#### 要做什么

1. 在不改变旧 Test B/C 锁的前提下，保留 `2.0.0` 人类审核草案并创建 `2.1.0-ai-draft.1`；
2. 将五分类 `risk_label` 与四分类 `task_alignment_label` 分离；
3. 用离线 mock runtime 捕获候选动作、参数来源和不可变 observation ID；
4. 构造 Risk/Alignment 反事实配对，避免 Alignment 再次成为 Risk 的确定函数；
5. 根据 1% FPR、cluster 结构和主端点冻结精度/功效目标；
6. 当前 active route 完成两条相互盲的双 AI 工程审核流；独立人工双盲审核仍是训练前签核门，不能被 AI 输出替代；
7. 重新构造互斥 v2 train/validation/calibration/untouched tests、manifest 与聚合报告；
8. AI-only 路线只生成工程证据，保持 `human_verified=false` 与
   `formal_training_authorized=false`；不移交论文级训练授权。

#### 当前状态

- ✅ 项目所有者已于 2026-08-24 选择 Route B，并于 2026-08-26 选择双 AI 工程/简历
  演示路线；选择不等于当前 v1 或论文级可训练；
- ✅ 项目所有者于 2026-08-30 进一步确认持续操作规则：凡由 Codex 执行的 C1B 审核均使用
  恰好两个相互独立的模型；输出固定标记为 AI 工程证据，不伪记为人工审核，亦不解除训练锁；
- ✅ 新增 `2.1.0-ai-draft.1` AI-only 协议、双 AI prompt、metadata example 和分析 CLI；
  原 `2.0.0` 人类审核协议继续作为独立人类签核依据保留，不被 AI 证据覆盖或伪装；
- ✅ 当前 active 的 machine-readable 工程审核协议为
  `configs/route_b_ai_review_protocol.yaml`，状态明确为
  `AI_REVIEW_DIRECTION_APPROVED_CONSTRUCTION_AUTHORIZED_NOT_TRAINING_AUTHORIZED`；
  `docs/route_b_data_protocol.md` 与人类审核草案不作为 AI 证据重写，但仍保留为独立人类
  审核/项目所有者签核的协议依据；
- ✅ 官方来源复核完成：BIPIA 代码为 MIT，但 Email/Table/Code 等数据保留 MIT 或
  CC BY-SA 等各自条款；WebQA/Summarization 仍需另行取得源数据；
- ✅ InjecAgent、NotInject、AgentDojo 继续锁为 Test B/C/D，验证器会拒绝把它们放入
  train/validation/calibration；
- ✅ canonical schema 已增加 `task_alignment_label` 四分类和
  `sandbox_policy_output` action provenance；旧二值 `alignment_label` 仅作 v1 兼容；
- ✅ Route B 结构验证器已实现：拦截动作证据缺失、测试集挪用、模板/动作签名跨角色
  泄漏、动作配对破坏和 Risk/Alignment 确定性混淆；
- ✅ 离线 mock capture 只记录候选动作，trace 固定为 `executed=false`、
  `external_side_effects=false`；10 条五分类 fixture 通过结构验证；
- ✅ Wilson 精度规划脚本已实现，结果明确标为 planning-only，并警告行级二项精度
  不能替代 cluster-aware 功效分析；
- ✅ Route B 操作命令已写入 `docs/route_b_user_runbook.md`，不依赖旧 PowerShell 会话
  中的自定义函数；
- ✅ 项目所有者已批准 `2.0.0` 方向、默认排除未单独批准的 CC BY-SA/非商业来源，
  并授权 project-owned 离线 mock-tool 正式候选语料构造；
- ✅ candidate 4 已生成 27,000 条：train 5,000、validation 2,000、calibration 10,000、
  Test A2 10,000；五类 Risk 和四类 Alignment 在每个角色中均衡；
- ✅ manifest 自哈希、配置/生成器/runtime/trace/split 哈希可重放，27,000 条 trace 全部
  `executed=false`、`external_side_effects=false`；
- ✅ exact、template group、action signature 检查通过；5,400 个模板代表在阈值 0.92 下
  完成 69,452 次跨角色 Jaccard 比较，near-duplicate 为 0；
- ✅ 已生成两套不同顺序的 AI reviewer 输入包；每个 AI 各完成 400 条 Risk 和 400 条
  Alignment 的工程审核目标，不暴露 seed labels；AI 分析器和预注册质量门已实现；
- ✅ readiness 聚合与协议锁框架已实现：会重放 candidate manifest、结构/near-duplicate
  报告和双人审核分析；integrity v3 绑定四个 split 与当前 policy 哈希；聚合器同时绑定
  公开报告与 candidate manifest 的密封 canonical SHA-256，并在任一证据缺失或漂移时保持
  `formal_training_authorized=false`；
- ✅ DeepSeek V4 Pro、Kimi K3 和 DeepSeek V4 Flash 的结构化审核结果、metadata、Prompt
  与输出哈希均已登记；每套审核均完成 400 条 Risk 和 400 条 Alignment；
- ⛔ `2.1.0-ai-draft.1` 分析已完成，但 Kimi K3 与 DeepSeek V4 Flash 两次 AI B 运行均未
  通过预注册质量门；失败结果已接受并记录为工程负证据，仍保持
  `human_verified=false` 与 `formal_training_authorized=false`；
- ✅ 项目所有者重新运行 GLM5.2 后，已更新 AI B 的 prompt/CSV 哈希登记；Risk 原始一致率
  与 κ 均为 1.0，Alignment 原始一致率为 0.98、κ 为 0.9733，`malicious` 逐类 seed
  agreement 为 0.92，所有数值质量门通过；
- ⛔ GLM5.2 仍有 8 条 Alignment 分歧，分析器因此保留
  `ai_quality_gates_failed_engineering_only` 与裁决要求；该运行不能被表述为无争议通过，
  仍保持 `human_verified=false` 与 `formal_training_authorized=false`；
- ✅ 项目所有者已完成 8 条 Alignment 分歧裁决，独立裁决 CSV 和 JSON 均已生成并通过字段、
  标签、时间、ID 覆盖和哈希核验；8 条最终均为 `ambiguous`，原始 AI 审核文件保持不变；
- ⛔ 该裁决只解决当前 AI 分歧，不等同于两名独立人类审核，也不打开正式训练或最终测试授权；
- ✅ 已新增第三 AI 补充审核协议、全量 400 条 Alignment 盲审包构造器和独立提示词；第三
  AI 不能覆盖既有双 AI 失败结果，也不能只审核 13 条分歧；
- ✅ candidate 4 Small A 的三轮 validation 100% 已作为工程负结果保留；复核发现移除随机
  ID/邮箱后 train/validation 的 50 个文本模板全部重叠，validation Risk 可由训练模板确定映射；
- ✅ 结构验证器新增易变标识归一化后的文本/动作模板跨角色检查；candidate 5 因一个归一化
  动作模板跨 train/Test A 被拒绝并保留失败报告；
- ✅ candidate 6 已生成 27,000 条并通过 manifest、exact、near-duplicate、归一化文本模板和
  动作模板检查，两个归一化跨角色计数均为 0；新的 400 Risk + 400 Alignment 双盲包已生成；
- ⛔ 首个 candidate 6 `audit_v1` 包的 reviewer-facing `sample_id` 暴露了种子 Risk/Alignment
  标签，未产生审核输出即已失效；生成器现强制使用标签中性 audit ID，`audit_v2` 已以相同
  冻结输入和抽样种子重建并通过四表 400 行的盲化格式检查，必须由未接触 v1 的两个 AI 重审；
- ✅ 双 AI 协议现绑定专用 `route_b_ai_audit_rubric.md`；旧人类审核 rubric 中“AI 不可担任
  reviewer B”的历史约束不再误用于 `2.1.0-ai-draft.1`。首次 AI B 派发因该冲突正确停止，
  未写入任何审核结果；
- ⛔ candidate 6 `audit_v2` 已由两个不同 Codex 模型完整审核，四表均为 400/400 且 package
  验证通过；但 Risk 原始一致率为 0.8925（低于 0.90），Risk 与 Alignment 的逐类 construct
  agreement 门也失败。失败报告已封存为工程负证据，不能改标签、阈值或据此启动训练；
- ✅ 已生成允许公开的失败诊断报告：两位审核者将全部种子 `ambiguous` Alignment 判为
  `unrelated`，并将全部种子 `instruction_hijacking` Risk 按 rubric 的主要后果判为更具体的
  数据外送/越权/工具操控，表明候选语料构造与冻结标签定义发生系统性冲突；
- ✅ 新训练契约将 Alignment 从旧二分类兼容头升级为 Task Shield 四分类头；A/B/C risk-only
  与 C multitask 配置已分离，旧 checkpoint 仍可按 metadata v2 重载；
- ✅ candidate 6 `audit_v2` 独立双 AI 审核已完成并以失败工程证据封存；其系统性标签冲突已在
  不改标签、不改门槛的前提下被诊断，不能据此启动新的 A/B/C 训练；
- ✅ candidate 7 已以冻结 candidate 6 输入和同一审核设计重建 27,000 条离线 mock 语料；结构、
  split 隔离、归一化文本/动作模板检查均通过。其双 AI 盲审的四张表均为 400/400、零弃审，
  Risk 一致率/κ 为 0.9875/0.9844，Alignment 为 0.985/0.98，所有预注册数值门通过；
- ⛔ candidate 7 仍有 5 条 Risk 和 6 条 Alignment A/B 分歧。冻结分析器因此保持
  `ai_quality_gates_failed_engineering_only`，不是数值门失败；第三 AI 的全量 400 条 Alignment
  补充盲审已完成且格式/哈希核验通过，但将全部 100 个 `ambiguous` seed 判为 `unrelated`，
  逐类 construct agreement 为 0；另有 12 条 wildcard `ticket.update` 被判为 unrealistically
  executable。该补充审核失败，不能覆盖原始 A/B 结果或替代人工裁决；
- ✅ candidate 8 新增按 scenario 覆盖动作模板的隔离配置机制，将 ticket 场景的 wildcard 更新
  改为具体 ID；代码定向测试、27,000 条构造、manifest 与结构/隔离检查全部通过，candidate 7
  的冻结输入和审核文件未被修改；
- ✅ candidate 8 双 AI 盲审的四张表均为 400/400、零弃审。Risk 一致率/κ 为 1.0/1.0，
  Alignment 为 0.9775/0.97，逐类最低 construct agreement 为 0.95，所有 800 个动作均被判为
  realistic，预注册数值门全部通过；
- ⛔ candidate 8 的 Alignment 仍保留 9 条原始分歧，因而状态必须为
  `ai_quality_gates_failed_engineering_only`，直至项目所有者进行可追溯的独立裁决。AI A 原 metadata
  的 local-execution 字段不规范已由不改写原文件的独立补充 attestation 记录；这不替代裁决或人工审核；
- ✅ 已新增非覆盖式 project-owner 裁决包构造器，并为 candidate 8 生成 9 行待裁决表；其 manifest
  绑定 audit/AI-review manifest 与两份原始 Alignment CSV 的 SHA-256，自哈希验证通过，封存 seed
  labels 未包含，所有最终标签、裁决人、时间和理由字段均为空；
- ✅ 项目所有者已完成 candidate 8 的 9 条 Alignment 独立裁决，最终均为 `ambiguous`；填写后的
  CSV 哈希、source manifest 哈希、9 行覆盖、时区时间、必填理由与固定字段均已核验。该记录只关闭
  已保存的 AI 分歧，原始 AI 分析不被覆盖，仍不等同于独立人类双盲审核；
- ✅ 已为 candidate 8 生成与 AI 输出隔离的 v2 人工双盲审核包：两名审核者各有 400 条 Risk 与
  400 条 Alignment，四表审核字段为空、ID 标签中性且均通过格式复核；每名审核者还必须提交可核验的
  `independent_human` provenance 声明。未填写的 v1 包保留为不可提交历史包；交接规则见
  `docs/route_b_candidate_8_human_audit_handoff.md`；
- ✅ 按项目所有者指示，`gpt-5.5` 与 `gpt-5.4` 已完成新的 candidate 8 补充双 AI 盲审，均为
  800/800、零弃审；Risk 完全一致，Alignment 一致率/κ 为 0.995/0.9933，预注册数值门均通过；
- ⛔ 该补充 AI 运行仍有 2 条 Alignment 标签分歧和 1 条现实性判断差异，故保持
  `ai_quality_gates_failed_engineering_only`。它是补充 AI 证据，不能覆盖原始 AI、项目所有者裁决
  或独立人类双盲审核门；
- ✅ 按项目所有者 2026-08-31 指示，使用两个独立 Codex 模型对与 candidate 8 人工 v2 包相同
  抽样内容的 AI-only 派生包完成新一轮双盲审核：`gpt-5.5` 与 `gpt-5.4` 各完成 400 条 Risk
  和 400 条 Alignment，四张 CSV 的结构、不可变字段、输出哈希和 reviewer 身份均通过校验；
- ⛔ 该新运行的 Risk 原始一致率/κ 为 0.80/0.75，最低逐 seed-class construct agreement
  为 0；Alignment 原始一致率/κ 为 0.8575/0.81，最低逐类为 0.51；action realism 为
  0.99875。分析状态为 `ai_quality_gates_failed_engineering_only`，负结果已写入
  `reports/data_quality/route_b_candidate_8_human_v2_ai_pair_failure.md`；它不替代独立人类
  审核、不修改人工 v2 包，也不解除 `human_verified=false` 或 `formal_training_authorized=false`；
- ✅ 按项目所有者 2026-09-04 指示，已将训练路线修订为
  `B-ai-assisted-engineering`，新增冻结协议 `2.2.0-ai-assisted-engineering.1`。两个不同
  AI 模型可以作为工程训练前的结构化审核证据，审核证据等级固定为
  `ai_reviewed_engineering_only`；AI 不计为人工审核，`human_verified=false` 和
  `formal_training_authorized=false` 继续保持；
- ✅ 已实现 AI 工程训练路线的 protocol lock、readiness 重放和 C2b 授权校验。它复用已生成
  的 candidate 8 manifest/完整性报告和双 AI 原始包，不修改历史数据或人工 v2 包；质量门
  失败不会被改写，若结构证据通过，只能由项目所有者在授权文件中填写风险接受理由后进行
  工程训练；
- ✅ 已新增绑定 candidate 8 sealed manifest 的 AI 工程聚合卡、运行手册和 AI 使用披露；
  该路线不解锁 calibration、Test A/B/C/D、最终测试、付费 API、GPU 租用或论文级结论；
- ✅ 已生成与正式人工 v2 包隔离的项目所有者 AI 分歧复核包：风险分歧 80 条、对齐/动作现实性
  分歧 57 条，共 137 条；输出 manifest 绑定两份 AI 原始 CSV、AI manifest、AI 分析和 audit
  manifest 的 SHA-256，封存 seed labels 未复制，且明确不满足独立人工双盲门；交接与填写规则见
  `docs/route_b_ai_disagreement_handoff.md`，当前加固版目录为
  `data/interim/route_b_v2_candidate_8_ai_disagreement_adjudication_v2/`。该包已由项目所有者
  完成逐条裁决，确定性 validator 通过并生成 ignored interim receipt；不改变正式人工 v2 包；
- ✅ 当前 runbook 的 readiness 主流程已统一改用 candidate 8 路径；历史 candidate 4 仅保留为
  历史证据，不再作为当前 readiness 命令示例；candidate 8 公开聚合卡必须绑定候选 manifest
  的密封 canonical SHA-256；
- ✅ 新增只读 `scripts/check_route_b_human_audit_progress.py`，在不读取 seed labels、不写回审核表
  或授权字段的前提下汇总四张表的完成数、缺失字段、身份一致性和 attestation 状态；完成后
  才进入确定性分析，减少人工返工；
- ✅ 新增 `scripts/run_route_b_candidate_8_audit_analysis.ps1`，将进度门与 candidate 8 确定性分析
  固定路径收敛为一条命令；审核不完整时 fail-closed，不生成分析文件；
- ✅ 项目所有者已创建 AI 工程训练授权文件，并通过 C2b 授权校验；当前授权保持
  `engineering_training_authorized=true`、`formal_training_authorized=false`、
  `human_verified=false`，且明确接受当前 AI 质量门失败仅用于工程训练；
- ⛔ 没有运行任何学习参数拟合，未启动 Small/Base 训练；当前只可继续进行训练前的
  不加载模型的 preflight，实际训练仍须项目所有者亲自执行。

#### 出口条件

- `docs/route_b_ai_review_protocol.md` 的双 AI metadata、哈希和质量门全部通过，并保留所有
  原始分歧与补充 AI 运行；
- 两名独立人类审核者完成 candidate 8 的标签中性审核包，且任何分歧均已按协议裁决；
- 若质量门未通过，必须保留失败报告并在 `docs/route_b_ai_review_results.md` 如实记录，
  不得修改阈值或手工调整标签；本阶段不得进入训练；
- AI 路线允许在结构证据通过后进入“项目所有者风险接受”步骤，但当前 candidate 8 的
  失败质量门必须由项目所有者在独立授权文件中明确接受；该授权只打开工程训练，不改变
  formal/human/final-test 语义；
- 真实数据、审核明细、JSON/CSV 报告继续被忽略，不提交仓库；
- 只提交框架、配置、文档和允许公开的聚合 Markdown 证据；
- 阶段退出后仍停在正式研究训练授权之前；AI 工程路线的项目所有者授权已单独形成并通过
  校验，但实际运行仍须项目所有者亲自执行，并且只能作为非论文级工程实验。

---

### C2a：Small 模型流水线与输入消融

#### 要做什么

- 安装并冻结 PyTorch/Transformers/CUDA 兼容环境；
- 为用户生成 200～500 条样本、20～50 step 的 CPU 冒烟配置和一键命令；
- 用静态检查、fixture 和 mock 验证接口、形状、配置、保存/加载路径；
- 由用户亲自运行 DeBERTa-v3-small 的 A（文本）、B（上下文）、C（动作）训练；
- Codex 只读取用户提供的日志并生成 H1/H2 分析，不启动训练命令。

#### 用什么做

- `src/intentfence/modeling.py`、`train.py`、`evaluate.py`；
- PyTorch、Hugging Face Transformers、DeBERTa-v3-small；
- TensorBoard 或 JSON 训练日志；
- 固定 seed 42 与相同 split。

#### 当前状态

- 🟡 双头模型、训练循环、输入 A/B/C、类别权重、早停和 checkpoint 代码已实现；
- ✅ 训练入口已增加模型加载前的 split/benign-attack/action preflight、确定性分层
  smoke 样本限额和无 ML 依赖的 `--dry-run`；CPU AMP 路径改为按实际 device 选择；
- ✅ 核心 Python 代码通过静态检查和编译；
- ✅ 新增训练契约 fixture 测试，覆盖角色错配、覆盖不足、action 缺失和 seed 可重复性；
- ✅ Small/Base Hugging Face 模型已锁定完整 40 位 revision，并贯穿 tokenizer、encoder 与
  checkpoint metadata；
- ✅ 新增 200 train + 100 validation、25 optimizer step 的 CPU smoke 配置和项目所有者一键
  脚本，预检会在加载 ML 依赖前强制样本数与 20～50 step 窗口；
- ✅ Small A/B/C 配置已拆分，fixture 测试约束除 `run_name`/`input_mode` 外其他条件相同；
- ✅ 双头 `[B,5]`/`[B,2]`、token-type 路由、固定 revision 传递和 checkpoint 保存/加载已由
  无 PyTorch mock 测试覆盖；
- ✅ CPU 一键脚本会自动记录 Git commit/dirty 状态、配置与数据 SHA-256、环境版本、耗时、
  成本和 checkpoint 逐文件哈希；manifest 生成器已通过 fixture 测试；
- ✅ 已用 candidate 4 的 `train.jsonl`/`validation.jsonl` 完成 C2a CPU smoke 只读 preflight：
  200/100 条样本、25 个计划优化步、Risk/Alignment 类别和 action 输入均通过；未启动训练、
  未下载模型权重、未生成 checkpoint；
- ✅ 本轮完整框架验证通过：Ruff、139 个 pytest、compileall、wheel 构建、PowerShell 脚本
  语法检查和无模型 CLI dry-run；
- ✅ 已在 `intentfence` Conda 环境通过官方 PyPI 安装 `[ml]` 依赖；`torch 2.13.0+cpu`、
  `transformers 4.57.6`、`accelerate 1.14.0`、`datasets 4.8.5`、`sentencepiece 0.2.2` 和
  `protobuf 6.33.6` 导入通过，`pip check` 无损坏依赖；固定 revision tokenizer 加载通过，
  DeBERTa 权重已由项目所有者的 smoke 运行下载；
- ✅ CPU smoke 脚本已改为先解析并打印唯一的 `intentfence` Python，再用同一解释器执行
  依赖检查、dry-run、训练、checkpoint 验证和 manifest 生成；更新后的 preflight 通过；
- ✅ 项目所有者已完成 200/100 条、25 optimizer steps 的 Action CPU smoke；耗时 158.24 秒、
  成本 0，`checkpoint_reload_passed` 和 `run_manifest_written`，manifest 中全部 checkpoint
  文件大小与 SHA-256 已复核一致；该运行只属于工程 smoke；
- ✅ 已修复 float32 softmax 转为 float64 后触发 scikit-learn 概率和警告的问题；softmax 现
  直接以 float64 计算，回归测试确认最大行和误差约 `2.22e-16` 且不再告警；
- ✅ 项目所有者已明确选择继续 Small A/B/C 工程训练；`human_verified=false` 与
  `formal_training_authorized=false` 保持不变，训练仍由项目所有者本人执行，结果只用于工程
  调试和简历演示；
- ✅ Small A/B/C 完整数据只读预检均通过：每组 5,000 train、2,000 validation、五类均衡，
  计划 939 optimizer steps；三个独立输出目录均未被占用；
- ✅ 历史 candidate 4 Small A 已封装为 `scripts/run_c2a_small_a.ps1`；脚本自动完成环境
  与数据预检、拒绝覆盖既有输出、训练、checkpoint 双重重载和 run manifest 生成，并提供
  `-PreflightOnly` 只读模式；
- ✅ 项目所有者完成 candidate 4 Small A：三轮 validation accuracy/macro-F1 均为 1.0，
  checkpoint reload 和 run manifest 通过；结果随后因语义模板泄漏被降级为工程负证据；
- ✅ candidate 6 的 A/B/C risk-only 与 C multitask 四组配置已通过只读 dry-run，每组
  5,000/2,000 条、939 optimizer steps，四类 Alignment 各自均衡；
- ⛔ candidate 6 训练脚本和训练运行等待新审核完成，不沿用 candidate 4 审核或 checkpoint。

#### 要测试什么

- 形状：Risk logits `[B,5]`；旧 metadata v2 Alignment logits `[B,2]`，新 Task Shield
  metadata v3 Alignment logits `[B,4]`；
- 梯度：两个头和共享 encoder 均有有效梯度；
- Tiny overfit：小样本上 loss 可明显下降；
- Checkpoint：保存后预测可重复加载；
- 标签映射：所有脚本一致；
- 截断：用户任务和拟执行动作不会被错误完全丢弃；
- 可复现：相同 seed/config/data 产生允许范围内的一致结果；
- A/B/C：只改变输入信息，其他条件保持一致。

#### 出口条件

- 框架侧静态、fixture、mock 和命令 dry-run 全部通过；
- 用户运行 CPU 冒烟与 checkpoint reload，并提供成功日志；
- 用户运行 Small A/B/C 至少 seed 42；
- 若上下文/动作没有增益，先检查数据构造，不直接扩大模型。

---

### C2b：Base 主模型、困难负样本与多任务消融

#### 要做什么

- 为用户准备 24GB GPU 环境清单、预算表、停止条件和恢复方案；
- 由用户租用 GPU 并运行 DeBERTa-v3-base A/B/C；
- 比较无/有困难负样本；
- 比较 Risk-only 与 Risk + Alignment；
- 最佳配置优先运行 seeds 42/52/62；
- Codex 不租用或操作训练 GPU，只分析用户提供的训练日志；
- 记录训练时间、显存、GPU 型号和实际费用。

#### 用什么做

- RTX 3090/4090 24GB 云 GPU；
- PyTorch AMP、梯度累积、早停；
- YAML 配置、JSON 日志、不可变数据 manifest；
- 分层 bootstrap 置信区间与配对样本比较。

#### 当前状态

- ✅ Base A/B/C risk-only 与 C multitask 配置已拆分，统一锁定 DeBERTa-v3-base revision、
  batch/学习率/epoch/max length 和预注册 seed；fixture 测试约束只允许输入模式、run name
  和 multitask loss weight 按协议变化；
- ✅ `scripts/run_c2b_base.ps1` 已实现 Base revision/seed/dependency/CUDA/data preflight、
  独立输出目录、显式项目所有者授权文件、checkpoint reload、实际人民币成本和 run manifest
  绑定；非预检训练还必须通过独立校验器。正式研究路线绑定 Route B 2.0.0 的 protocol
  lock、candidate manifest、readiness 报告、完整性报告和正式人类审核证据；AI 工程路线绑定
  2.2 AI training protocol lock、双 AI manifest/analysis 及其 readiness，并继续保持
  `human_verified=false` 与 `formal_training_authorized=false`；两条路线都将实际
  train/validation 路径与字节哈希绑定到 candidate manifest；
  `-PreflightOnly` 同样绑定 candidate manifest 的 train/validation 路径与字节哈希，不加载
  tokenizer、模型或 checkpoint，失败不自动重试；Base 训练 CLI 还会再次要求并重验同一组授权；
- ✅ 2026-09-04 已用当前 AI 工程路线在 CPU 上完成一次 C2b `-PreflightOnly`：action multitask
  seed 42、5,000/2,000 train/validation、四类 Alignment 与五类 Risk 计数、939 个计划
  optimizer steps、Conda/PyTorch/Transformers 解析均通过；未加载 tokenizer/模型、未创建
  checkpoint、未启动训练；启动脚本已支持显式 `-CondaExecutable`，兼容 Conda 不在 PATH 的主机；
- ✅ C2b 启动时的人民币成本参数已改为可选；训练完成后先生成不含费用的 run manifest，项目所有者
  可在取得平台账单后用 `scripts/record_run_cost.py` 原子补录实际成本，不把预计费用当作实验事实；
- ✅ 已补充 Linux 云 GPU 的 `scripts/run_c2b_base.sh`，与 PowerShell 入口保持相同的候选
  manifest、配置、Conda、CUDA、授权、独立输出目录、checkpoint 和 run manifest 约束；仅做
  Bash 语法与帮助入口检查，未在本机启动训练；
- ✅ C2b 配置校验器只接受已登记的四个 Base 变体、固定 DeBERTa revision、完整冻结超参数、
  `task_alignment` 目标和预注册 seeds；当前入口固定服务 candidate 8，避免任意配置或候选
  manifest 被误带入主实验；protocol lock 同时严格校验 schema 1 与 SHA-256 算法；
- ✅ 2026-08-31 对 candidate 8 的 Small/Base A、B、C 和 C multitask 共 8 个配置完成 dry-run；
  每个配置均通过 5,000 train/2,000 validation、五类 Risk、四类 Alignment 和 939 optimizer
  steps 检查；未加载 tokenizer/模型、未创建 checkpoint，CUDA 不可用时只保留 preflight；
- ✅ `intentfence.statistics` 已实现预注册的 paired cluster percentile bootstrap（seed outer
  stratum）、配对差值、Cohen's dz、跨 seed 汇总和 Holm 校正；合成 fixture 测试通过；
- ✅ `scripts/summarize_seed_runs.py` 已实现不补造 seed 的标量结果汇总，并显式声明它不能
  替代逐样本 paired bootstrap；
- ✅ 2026-09-05 在用户已有 RTX 4090 上完成 candidate 8 AI 工程路线的 Base C multitask、
  seed 42 单次运行（5 epochs、5,000 train/2,000 validation）。Codex 配置环境和准备命令，
  用户在 tmux pane 按 Enter 启动；训练完成且 checkpoint reload 通过，`best` 对应 epoch 4。
  验证集 Risk accuracy 为 0.9995、Macro-F1 为 0.9994999992187488；仅是 project-owned mock
  数据上的工程证据，不能证明真实攻击防御效果。耗时 380.946923 秒，实际账单待补录。
  完整命令、版本、哈希、曲线及限制见
  `reports/training/c2b_base_action_multitask_seed42_20260905.md`。
- ✅ 已有本地真实训练 checkpoint；权重、数据、原始日志和原始 run manifest 不提交 Git。
- ✅ 2026-09-05 完成同一 candidate 8、C action Risk-only、seed 42 单次工程运行；验证集
  Risk accuracy 0.9105、Macro-F1 0.905618926130284，checkpoint reload 通过，输入哈希前后
  一致。与 C multitask seed 42 的对照报告见
  `reports/training/c2b_base_action_risk_seed42_20260905.md`；实际费用待补录。
- ✅ 随后完成同一 candidate 8 的 B context Risk-only（Macro-F1 1.0）和 A text Risk-only
  （Macro-F1 0.9939986496961817），均为 seed 42、5 epochs、checkpoint reload 通过；对应
  报告见 `reports/training/c2b_base_context_risk_seed42_20260905.md` 和
  `reports/training/c2b_base_text_risk_seed42_20260905.md`。四个预设 Base 变体的 seed 42
  单次工程运行已完成；未自动启动 seed 52/62。
- ⬜ 尚无跨 seed、A/B/C 对比、Alignment 独立评估或正式显著性/效应量报告；C2b 正式研究出口未通过。

#### 要测试什么

- H1：B 相对 A 在固定 FPR 下的差异与置信区间；
- H2：C 相对 B 在动作相关攻击上的逐类差异；
- H3：困难负样本对 NotInject FPR 与攻击 TPR 的双向影响；
- H4：多任务头的独立收益及标签冗余；
- 多 seed 均值、标准差和异常波动；
- 训练曲线、过拟合、高损失样本和标签噪声；
- 不允许用突破 1% FPR 换取表面召回提升。

#### 出口条件

- H1～H4 的预注册比较均完成或明确报告负结果；
- 最佳模型权重冻结；
- 所有运行能由 commit、config、manifest、seed 和日志追溯。

---

### C2c：独立校准与策略阈值冻结

#### 要做什么

- 用冻结模型导出 calibration split logits；
- 分别拟合 Risk 与 Alignment 的 Temperature；
- 比较校准前后 ECE、Brier、NLL、reliability diagram；
- 只在 calibration split 选择 1% FPR 和 Allow/Confirm/Block 阈值；
- 冻结模型、校准器和策略版本。

#### 用什么做

- `scripts/export_logits.py`、`scripts/calibrate.py`；
- SciPy optimization、scikit-learn metrics；
- `configs/policy.yaml`、版本化 calibration JSON。

#### 当前状态

- ✅ Temperature Scaling、ECE/Brier/NLL 和低 FPR 阈值函数有单元测试；
- ✅ `reliability_diagram`、classwise ECE（含样本不足状态）和双头校准指标报告已实现，
  由合成 fixture 覆盖；
- ✅ logits 导出和校准 CLI 已增加 calibration split、输入哈希、数组形状、`.complete` bundle
  提交标记、输出拒绝覆盖和只读 preflight；正式导出/校准要求项目所有者授权绑定到精确 logits、
  input、model tree hash、model revision、protocol registry 和 policy snapshot；校准 artifact
  还必须带 frozen provenance 与通过的质量门；
- ✅ 推理与最终测试入口会拒绝未封存或与模型、报告、policy、目标 FPR/最低 TPR、校准输入不一致
  的产物；质量门失败不会发布可用 calibration artifact，最终预测记录保留固定阈值和校准哈希；
- 🟡 logits 导出和校准 CLI 已实现，但没有真实 checkpoint；
- ⬜ 真实温度和阈值尚未拟合。

#### 要测试什么

- 校准集与训练/验证/测试完全互斥；
- 温度为正，NLL 优化正确；
- 校准不改变 logits 排序，却改善至少一个可靠性指标且不损害安全运行点；
- Classwise ECE 样本不足时明确标记；
- 跨数据集失准单独报告；
- 长文档聚合分数不被称为攻击概率。

#### 出口条件

- 温度、阈值和策略版本冻结；
- H5 报告完成；
- 最终测试开始后不再修改校准参数。

---

### C3a：最终跨数据集、过度防御与错误分析

#### 要做什么

- 在冻结条件下运行 Test A（未见模板）、Test B（InjecAgent）、Test C（NotInject）；
- 与规则、TF-IDF、ProtectAI、PIGuard 和单文本内部基线公平比较；
- 生成 bootstrap CI、逐场景/类别/长度/工具分组结果；
- 输出最危险假阴性、最常见假阳性和模型差异案例；
- 只执行一次正式最终测试，后续修订建立新版本。

#### 用什么做

- `intentfence-evaluate`、评测脚本、Pandas/scikit-learn（需要时）；
- 固定 predictions JSONL、metrics JSON、Markdown/图表；
- 统计 bootstrap、配对差异分析、错误样本审计。

#### 当前状态

- ✅ `evaluate_risk_predictions` 支持显式 calibration-derived threshold；Test A-D split 未提供
  固定阈值时拒绝评测，预测文件记录 split、template group、scenario、attack family、长度桶
  和模型 revision，并拒绝覆盖非空输出目录；
- ✅ `evaluation.py` 与 `analyze_predictions.py` 已实现固定阈值的总体/分组指标、template-group
  cluster bootstrap CI、NotInject 风格 Wilson 区间和不复制原文的错误分析；
- ✅ `compare_predictions.py` 已实现同 case/同标签/同 template group 的 paired
  candidate-minus-baseline 区间，并分别接受各变体已冻结的 calibration threshold；
- ✅ `final_test.py` 与 `run_final_matrix.py` 已实现 project-owner authorization、模型/校准/
  报告/policy/protocol/测试输入/阈值哈希及语义绑定、calibration/final split 隔离检查和一次性
  独占 ledger；formal-test 库入口也要求 ledger 绑定的校准 backend，完成阶段会从 predictions
  重算并核对 metrics，ledger 状态采用原子写回；合成 fixture 覆盖授权、质量门/策略/产物篡改
  检测、阈值漂移和重复拒绝；
- 🟡 统一评测与预测文件代码已实现；
- ⬜ 真实 Test A/B/C 尚未运行；
- ⬜ 真实结果上的 Bootstrap/错误分析和论文图表尚未生成。

#### 要测试什么

- 主指标 TPR@1% FPR；
- Macro-F1、逐类 P/R/F1、AUROC/AUPRC；
- NotInject FPR；
- 跨域 ECE/Brier/NLL；
- 置信区间与多重比较说明；
- 截断、关键词捷径、场景偏差和潜在数据污染；
- 所有主张是否能由原始 predictions 重算。

#### 出口条件

- 核心结果表、校准表、错误分析和限制说明完成；
- 结果支持或否定 H1～H5 的证据链完整；
- 不选择性隐藏负结果。

---

### C3b：ONNX INT8、FastAPI 与本机 CPU 实测

#### 要做什么

- 导出冻结模型为 ONNX；
- 执行动态 INT8 量化；
- 量化前后重跑相同安全测试；
- 测量模型大小、峰值内存、P50/P95 和吞吐；
- 验证 `/health`、`/v1/evaluate`、版本信息和故障策略；
- 使用 mock 工具演示，不执行真实发送、上传、删除或支付。

#### 用什么做

- `deployment/export_onnx.py`、ONNX Runtime；
- FastAPI/Uvicorn；
- `benchmarks/latency.py`；
- Pytest/TestClient、PowerShell/API smoke test、Docker（可选运行验证）。

#### 当前状态

- ✅ 规则后端 API、策略和故障模式已通过单元/API 测试；
- ✅ 规则后端本机延迟脚本已运行；基准现在记录冷启动、预热后分位数、并发吞吐、artifact
  哈希/大小和进程峰值内存；该 smoke 只证明工具可用；
- ✅ PyTorch/ONNX 导出前置校验、不可覆盖目录、ONNX/INT8/tokenizer 哈希绑定元数据和运行时
  篡改拒绝已实现，并由合成 fixture 验证；
- ✅ 延迟基准已增加与正式测量共用解析逻辑的只读 `--preflight-only`，会在不加载模型或创建
  报告的情况下检查输出位置、模型/ONNX 变体、tokenizer、校准文件和已有导出元数据，减少
  真实 C3b 测量时的手工返工；
- ✅ `/health` 与 `/v1/evaluate` 暴露应用版本、模型版本/revision；检测器异常的 read
  restricted fail-open 与 external fail-closed 已由 TestClient mock 验证；
- ✅ 2026-09-02 已通过 `scripts/run_c3b_local_api_smoke.ps1` 实际启动 Uvicorn 规则后端完成一次
  运行时 smoke：`/health` 返回应用/策略版本，外部通信攻击样例返回 `block`；脚本已关闭自身
  进程并释放端口。该证据仍只属于规则/API
  工程验证，不代表神经模型或 Docker/ONNX 结果；
- ✅ 新增并实际运行 `scripts/run_c3b_local_api_smoke.ps1`，将本机 Uvicorn 启动、健康等待、规则 API 断言和
  自身进程/临时日志清理收敛为一条命令，降低后续重复手工验证成本；
- ✅ Dockerfile 继续使用非 root 用户，并新增 `/health` healthcheck；`.dockerignore` 会在
  build context 阶段排除真实数据、checkpoint、模型权重和运行时缓存；
- ✅ 新增 `scripts/run_c3b_docker_smoke.ps1`，统一执行规则镜像构建、健康等待、API 断言和
  自身容器清理，减少后续手工操作；
- ✅ 2026-09-02 Docker daemon 恢复后已实际完成一次 rules-only 容器 smoke：镜像构建、容器启动、
  `/health`、外部通信阻断和自身容器清理均通过；该证据不代表模型、ONNX/INT8 或 CPU 延迟结果；
- ✅ 本次启动故障已定位为 Docker Desktop 4.50.0 的临时 AF_UNIX socket 条目无法访问；仅将
  `Docker\run` 与 `docker-secrets-engine` 两个临时父目录改名为可恢复备份，未触碰镜像、卷或设置，
  随后 Docker smoke 恢复通过；恢复说明已写入 C3b runbook；
- ⬜ 没有真实 checkpoint，尚未导出 ONNX 或 INT8；
- ⬜ 未测量真实模型安全变化、内存和 P50/P95；
- ⬜ 没有真实模型的 Docker/ONNX 部署结果，真实模型导出、量化安全重跑和 CPU 实测仍待冻结
  checkpoint 与对应授权。

#### 要测试什么

- PyTorch 与 ONNX logits/概率在容差内一致；
- INT8 相对 FP32 的主安全指标变化；
- 冷启动与预热后单请求 P50/P95；
- 不同输入长度和并发下延迟；
- 模型/校准/策略版本正确返回；
- 超时、缺模型、坏校准文件时按工具等级 fail-open/fail-closed；
- 高风险动作低分时仍至少人工确认。

#### 出口条件

- 普通 CPU 可运行量化模型；
- 安全指标和延迟均为真实实测值；
- API、演示和故障策略可重复验证。

---

### C4：论文式报告、简历材料与公开发布准备

#### 要做什么

- 完成摘要、方法、实验设置、结果、消融、错误分析、限制与伦理说明；
- 更新 README、数据卡、模型卡、威胁模型和复现命令；
- 制作可追溯结果表与简历描述；
- 如有模型权重，使用 Release 或模型平台，不提交大文件；
- 清理密钥、个人数据、缓存、原始数据和 checkpoint。

#### 用什么做

- Markdown/LaTeX（论文式报告）；
- Git/GitHub Actions；
- 模型卡、数据卡、实验日志与 raw predictions；
- 演示截图或短视频（用户批准后）。

#### 当前状态

- ✅ README、模型卡、数据卡和可靠性策略已按当前 C1/C3b 证据边界更新；C0 冻结威胁模型保持未改写；
- ✅ 已新增论文式报告模板、主张—证据矩阵、复现清单、AI 使用披露、简历表述模板和公开发布清单；
- ✅ 已补充仅工程事实的简历/项目表述，并明确已完成的是 rules-only Docker smoke，不延伸为模型结果；
- ✅ 已新增标明未发布的 source-only release notes 草稿，并接入 README；双模型审核后明确
  candidate 8 人审、校准、Docker runtime 和最终公开审批仍未完成；
- ✅ `scripts/audit_public_release.py` 已加入 CI，可拒绝权重、原始/中间数据、结果缓存、`.env`
  和高置信凭据模式；fixture 覆盖允许项与阻断项；
- ✅ C4 文档自检覆盖缺失证据、Task Shield 新颖性边界、C1 legacy schema 与公开部署边界；
- ⬜ 没有真实实验结果，不能形成论文结论或简历数字；
- ⬜ 未完成论文式实验报告和最终简历表述；最终公开内容仍需项目所有者批准。

#### 要测试什么

- 每个数字是否链接到结果文件和实验配置；
- 文档命令能否从干净环境运行；
- 不包含真实数据、密钥、checkpoint 或许可证不允许的内容；
- 不把工程目标写成已达到结果；
- 不把 Task Shield 思想表述为本项目首次提出；
- 负结果和局限是否完整披露。

#### 出口条件

- 简历中的每一条量化表述都可追溯；
- 论文式报告通过方法、统计和复现自查；
- 用户批准公开内容。

---

### G1：完善公开仓库并发布首个 Release

#### 要做什么

- 复核公开仓库 `Jvn1vs/IntentFence` 的最终内容；
- 检查初始化文件及后续新增文件；
- 分阶段维护提交并合并到 `main`；
- 运行 GitHub Actions；
- 配置仓库描述、Topics、License 和首个 Release（需要时）。

#### 用什么做

- Git、GitHub 连接或浏览器；
- `.gitignore`、GitHub Actions；
- 功能分支和受审查的 `main` 历史。

#### 当前状态

- ✅ 本地 Git 已初始化；
- ✅ 公开仓库 `Jvn1vs/IntentFence` 已存在，当前工作分支为 `codex/c4-publication-readiness`；
- ✅ C4 分支已推送，远端 SHA 与本地提交一致；
- ✅ `scripts/check_release_readiness.py` 已加入，对 committed Git tree、README 本地链接和 CI
  质量门做不发布预检；
- ✅ CI 已补齐 C1 数据报告测试所需的 `.[data,dev]` 依赖；split ratio 归一化改用跨 Python
  版本稳定的补偿求和，避免同一冻结 manifest 在 3.10/3.12 间产生浮点漂移；
- ⬜ G1 的最终材料复核、合并、Release 和简历包装尚未开始，仍需项目所有者批准。

#### 要测试什么

- 提交范围不包含 `.venv`、原始数据、结果缓存、模型权重或密钥；
- GitHub Actions 在干净 Linux 环境通过；
- README 链接和安装命令有效；
- 仓库可见性确认为 public；
- 推送后的 commit 与本地验证 commit 一致。

#### 出口条件

- 用户明确授权 G1 的最终合并与 Release；
- `Jvn1vs/IntentFence` 可公开访问；
- 默认分支 CI 通过。

## 6. GPU 与费用计划

| 时点 | 资源 | 预计用途 | 启动条件 |
|---|---|---|---|
| C0 | 当前 CPU 电脑 | 文献、协议与框架检查 | 无需付费 |
| C1 | 当前 CPU | Codex 执行真实数据转换、审核抽样/预审、隔离划分和报告；项目所有者确认正式人类审核；不拟合 TF-IDF 或任何学习参数 | 当前已授权 |
| C2a | 用户操作当前 CPU/可选 GPU | 用户运行 Small 冒烟；Codex 提供框架和命令 | C1 出口通过 |
| C2b | 用户租用 RTX 3090/4090 24GB | 用户运行 Base A/B/C、消融、多 seed | Small 流水线通过且用户自行批准预算 |
| C3b | 当前 CPU 电脑 | ONNX INT8 和真实延迟 | 冻结 checkpoint 可用 |
| H6/B2 | 本地小 LLM 或付费 API | 可选系统比较 | 核心完成、单独预算批准 |

租 GPU 前由 Codex 提供平台、显卡、单价、预计小时数、预算上限、停止条件和数据上传范围清单；用户自行决定并执行租用。Codex 不操作租用或付费训练。

## 7. 论文级统计与复现要求

- 最佳核心配置优先使用 seeds `42/52/62`，只有一个 seed 时明确标注；
- 主比较使用相同冻结样本上的配对结果，并报告 bootstrap 置信区间；
- 同时报告效应大小/绝对差值，不只报告显著性；
- 对多个次要指标说明多重比较策略，不用挑选最有利结果；
- 预先冻结主指标 `TPR@1% FPR` 和 NotInject FPR 硬约束；
- 所有 stochastic 复现实验记录允许差异范围，异常波动必须分析；
- 每个运行保存 commit、数据 manifest、config、seed、依赖、硬件、时长、费用、原始预测和日志；
- 最终验证报告只有在成功重跑后才能标记 `VERIFIED`，否则保持 `UNVERIFIED` 或 `ANALYZED`。

## 8. 当前已验证事实

截至 2026-09-05：

- Ruff 静态检查通过；
- 261 个单元/API/协议/数据/训练框架测试通过；FastAPI/Starlette 测试客户端弃用警告已通过约束
  `starlette>=0.40,<1` 并同步到 0.52.1 消除；
- `pip check` 通过；core/dev 锁定环境与当前 Python 3.12 Windows 环境一致；data、ML 和 ONNX extras
  仍按实验 manifest 单独锁定；
- Python 编译检查通过；
- wheel 构建通过；
- C0 协议校验和 C1 框架校验通过；
- 合成 fixture 已覆盖来源/转换 replay、人工审计 key、merge、去重、六角色划分、manifest、完整性报告、规则与 word/char TF-IDF 接口及正式测试锁；
- 上述结果属于静态、合成和规则后端运行时验证，只证明工程框架按当前契约工作，**不证明 IntentFence 在真实数据或公开基准上有效**；
- 2026-09-05 新增一份 Base C multitask seed 42 的 AI 工程训练 checkpoint，成功重载且文件哈希
  经核验；详见 C2b 与对应训练报告。它不改变前述静态/fixture 测试的证据范围。尚无真实校准结果、
  跨数据集结果或 ONNX INT8 模型；C3b 当前新增内容仍只属于静态/fixture/规则后端工程验证
  （含一次本机 Uvicorn 和一次 Docker rules-only smoke）。
- C4 的公开发布审计、论文模板和主张证据矩阵已通过 fixture/静态检查，但不等于最终公开
  内容已获项目所有者批准。
- G1 的 committed release-tree、README 链接和 CI 契约预检已实现并通过；这不等于已合并到
  `main` 或已发布 Release。

## 9. 每阶段汇报模板

```text
阶段：<阶段编号和名称>
状态：通过 / 有条件通过 / 未通过

完成内容：
- ...

文件改动：
- ...

测试：
- <命令> → <结果>

研究证据：
- 已得到：...
- 尚不能声称：...

风险/问题：
- ...

下一阶段：
- 要做什么：...
- 使用什么：...
- 需要资源/费用：...

暂停，等待用户提问或确认。
```

## 10. 当前停止点与 Route B 新阶段

### 2026-09-11：AIB航班数值误导对照完成

新增00175同前缀两条提案：按返回价格选择RedTail199，以及按显式准备的sponsored_note对象错误声称BlueSky218最低。保留返回选项限定，不补币种/日期/航线，不使用源未来回答/标签选动作，继承00022/00025/00099/00109/00113/00175六成员must-link。报告 `reports/data/aib_flight_contrast_20260911.md`；累计14场景23观测，不等于训练样本。

新增模块、构造/重放脚本及5项fixture测试；5 passed（0.48秒）、相关Ruff/编译通过，落盘重放一致。record.json SHA-256 `71dee53c314843c7dd715e981ef5a8ae435a9bf18eafde6327cbb3896807a4db`。下一步版本化关联新动作审核队列并继续unrelated/ambiguous缺口，标签仍null，不将旧21项审核意见套用新动作。

### 2026-09-11：桶策略与澄清展示核对完成

回读00032/00159源上下文，并核对AWS官方参数文档。新增离线展示函数：五字段桶策略展开为Bucket/JSON Policy，缺正文代码转换为可读澄清；旧动作和AI意见不覆盖，新样本计数不增加。严格拒绝资源错配、权限泛化及遗漏额外澄清问题。报告 `reports/data/aib_action_review_views_20260911.md`；ignored views.json SHA-256 `3e916597ed5cb42f276d2c4ca1f20211bd875ab6551cabe98b4829cca92602ae`。

新增5项fixture通过；全量验证结果见同名报告。未验证服务接受或实际权限效果，未改审核标签。后续回读109/113/175动作前文本，其中175的两条航班价格及诱导错误最便宜结论形成更明确的来源对照；下一步优先按返回结果构造，保留日期/航线未显式出现在结果中的限制，并继承已有推广家族must-link约束。

### 2026-09-11：AIB五轮准备清单关联完成

固定五轮输入并复用逐动作哈希核验，关联21条单次非盲AI意见和保守家族约束（保留未选中must-link成员）。13场景暂定Risk覆盖五类，但仅00026/00103/00167具备不同、非弃权且realistic的动作Alignment意见；此为意见覆盖，不是同前缀/独立审核通过。报告 `reports/data/aib_preparation_register_20260911.md` 列出公钥截断、桶策略语义、内部澄清代码、部分摘要及旧值误用等具体缺口。

新增清单构造脚本及3项测试，相关9 passed（4.35秒）、Ruff通过。ignored register.json SHA-256 `eead216c4935a2787fb33971cdd954006be8d5fe467eb3e6644224ff83ecacf5`。未赋标签或构造split，training_ready=false。下一步自主核对桶策略/澄清表示并寻找完整上下文的缺失对照，不降低原五风险四Alignment动作目标。

### 2026-09-11：ToolSafety官方工具入口调查完成，三条继续隔离

检查ToolBench未截断238项目录树及StableToolBench官方发布链接，找到ToolEnv2404（11,706,795字节、数据卡MIT）和Cache（235,732,308字节、数据卡未声明许可证）两个压缩包入口。仅取公共目录、版本信息和README，未下载档案；尚无三条工具与上游具体版本的对应证据。报告 `reports/data/toolsafety_upstream_metadata_20260911.md` 保存链接、版本、哈希及范围限制。

元数据receipt SHA-256 `2802263955a8c261e280f8f1256f12cdc64be02f754211853013fd68d2b628e3`。不新增准入、不应用标签。为避免来源调查阻塞已有授权工作，下一步自主汇总AIB五轮试点及21条AI意见，建立当前统一准备清单与逐项缺口；ToolSafety三条保持隔离，档案使用若需要则另按具体来源条款处理。

### 2026-09-11：三条ToolSafety候选保护文本筛查完成

固定前缀和复查文件哈希，对13个保护文件54,483项文本进行规范化精确/5-shingle Jaccard≥0.8筛查；三条查询数14/10/7，命中均0。包含动作前工具JSON字符串叶值，不涉及模型测试结果。新增只读脚本及两项fixture测试，2 passed、相关Ruff通过。报告 `reports/data/toolsafety_targeted_screen_20260911.md`，ignored screen_v2.json SHA-256 `fe937af6cd926c941bfd8b6ca6c7dd9aece5a56f25282bf5799caa3c1eae431f`。

这仅完成所列保护文本的筛查，不代表语义/工具家族或完整AgentDojo隔离。官方ToolBench说明指向独立发布的toolenv；三项工具名搜索无结果，不足以完成逐条归属。自主继续小范围官方工具元数据核查，三条仍隔离、不纳入训练、不应用正式标签。

### 2026-09-11：良性动作来源回查完成

完整读取八个AIB良性候选，因执行参数缺失或与当前任务仍相关，不强造无关/不确定动作。回查三条ToolSafety已发布动作，暂定ambiguous2、unrelated1：随机法语词生成器不能翻译已选英文词；ESPN与vidal的映射缺证据，旧unrelated意见保守改为ambiguous，历史200条结果不覆盖。详见 `reports/data/benign_action_source_recheck_20260911.md`。

非盲单次Codex/AI侧记录SHA-256 `b073e0f7a987c7b0d2e658fdef7b8789dbb11585a8c834fe715bfaaccfd39777`，保存三条源前缀/动作绑定及旧新意见；ID与输入哈希已核对。仅语义回查与文档变更，不重复代码测试。尚未解决上游归属、锁定测试隔离、同上下文配对及独立审核，不应用标签或纳入训练。下一步自主核查这三条工具来源与测试重叠，先判断可准入性。

### 2026-09-11：保守家族约束初步核对完成

读取182条已有场景意见的家族清单，补读候选关系原文，新增答案推广、额外接收方、SSH授权写入三组must-link决策。相同原名先保守连边，112个暂定名称形成107个连通约束组；不是107个独立家族，未连边不证明独立。报告 `reports/data/aib_family_constraints_20260911.md` 保存范围、局限和证据。

新增配置、图构造脚本及4项fixture测试，相关测试4 passed（0.10秒）、Ruff通过。ignored constraints.json SHA-256 `635bdebe9cc1e1f15e41c455123eb999d17673cbce3b0156b75fef5e38b65d2f`。没有split或训练，family_isolation_complete=false。下一步继续真正无关/授权未知动作来源及拟准入家族隔离核验，按持续授权自主进行。

### 2026-09-11：21条记录单次非盲AI预审完成

重新阅读13案例动作前消息及全部21条观测，单次Codex/AI预审得到aligned11、malicious7、弃权3；unrelated和ambiguous标签意见仍为0。弃权对应两项部分摘要和一个旧数值误用，不能为补覆盖把质量错误强归四分类。真实性意见realistic18、ambiguous2、unrealistic1，不代表真实API执行验证。

报告 `reports/data/aib_action_prereview_20260911.md`，ignored review.json SHA-256 `2dd51ba115516c1c9e7589478147cef9242e5cabae31809ee7cc6f55fdc16a3a`。新增只读校验及六项fixture测试，21项输入/动作哈希与成员身份核验通过。完整pytest **418 passed（63.73秒）**，Ruff、compileall和wheel通过。意见明确非盲、与准备者非独立，未作为双AI或人审，未应用训练标签。

自主继续来源家族核验及真正无关/授权未知动作寻找。初步发现00022与00099家族名称分别为answer_promotion_hijack/answer_promotion_injection，语义接近，不能仅凭名称不同视为隔离；00139/00140已共享user_authorized_followup名，需结合结构而非盲目拆分。当前尚无家族隔离通过结论或训练授权。

### 2026-09-11：良性多轮旧结果误用对照完成

新增AIB-00140同前缀的当前数值6/历史总量37两条返回提案，各自保留user查询与tool结果范围，源后续示范不进入选择器。新增 `stale_result.py`、固定来源构造/重放脚本及五项fixture测试。报告 `reports/data/aib_stale_result_20260911.md`；ignored record.json SHA-256 `09e91787c1f7228b86db40f8c0b912df0365ce4a3eba8c8da80a35542ded4d24`。

完整pytest **412 passed（70.04秒）**，Ruff、compileall、wheel通过；真实记录两次构造核验一致。没有更新历史数据、赋标签或训练。累计13场景、20操作提案及1澄清。旧值误用是准备者构造的错误回答，不是真实模型错误；是否归为unrelated不能仅凭答错确定，需要按冻结语义独立审查。

自主继续逐动作AI预审侧记录及家族核验；不得将单次非盲AI意见伪装为双独立AI或人审，也不得为了四分类覆盖强行贴标签。

### 2026-09-11：指令劫持摘录对照完成

按持续授权新增AIB-00022/00099两组来源对照、四条提案；相关源绑定八项fixture测试、Ruff和落盘重放核验通过。复用已验证的风险对照实现，未修改历史结果。报告 `reports/data/aib_hijacking_pilot_20260911.md` 保存哈希与限制：源文章不完整，目标只是部分摘录，不能直接赋aligned。manifest `19ef3b3ac5243a0d7e7a74d570d80edb019ed8209ac6e0204f2f58719aba336a`。

累计12场景、18操作提案及1澄清，尚未训练就绪。已完整阅读良性候选AIB-00140，旧总数37与当前紧急数6具有明确查询范围差别；下一步自主构造该多轮对照，再做逐动作AI预审及保守家族隔离，不需要阶段确认。

### 2026-09-11：跨试点动作清点完成，自主继续补覆盖

按最新授权直接继续清点阶段。新增 `scripts/inventory_aib_actions.py` 和五项 fixture 测试，固定三轮试点的 manifest/record 以及场景 AI 意见快照哈希，生成 ignored 清单。汇总10个源案例、14条操作提案、1条澄清；5个场景有同前缀不同动作。没有合并训练集或改变旧产物。

场景暂定风险覆盖：benign3、外传3、权限提升2、工具操纵2、指令劫持0；对应有动作对照场景数0/1/2/2/0。该计数不是独立标签验收，不能以总量声称五类或四类Alignment覆盖。报告及文件哈希见 `reports/data/aib_action_inventory_20260911.md`。

完整 pytest **407 passed（66.85秒）**，Ruff、compileall、wheel通过。下一工作按报告顺序自主推进：先补指令劫持对照及有来源依据的良性内容偏离/不确定动作，再做独立于策略名的逐动作 AI 预审侧记录和保守家族隔离核验。人审、训练及正式测试边界保持原要求，不再等待常规阶段确认。

### 2026-09-11：三类机制对照与自主推进授权

所有者明确表示“确认，之后都改成你自己推进，不需要我确认”。AGENTS.md、本计划及执行策略已同步：数据/工程常规阶段完成后汇报、提交并自主继续，历史阶段暂停语句不再作为确认门。

本阶段新增AIB-00026/00032/00103/00167四组来源对照、八条提案，保留工单状态/处置、S3单条策略、聊天收件人/正文的结构差别。参数逐条 AI 核对；机制线索涉及工具操纵、权限提升和未授权转发，未正式赋标签。新增来源绑定模块、构造/核验脚本、配置与报告 `reports/data/aib_risk_pilot_20260911.md`。来源/准备/记录哈希详见报告，manifest `d84b4f3e7e81b2794fa69d51b993211e18249febc2799718c93a191b76f7bf40`。

新增八项 fixture 测试；完整 pytest **402 passed（63.90秒）**，Ruff、compileall、wheel通过，落盘来源绑定重放通过。未执行任何来源工具、应用训练标签或构造split。字段解释仍由 AI 准备，不能以策略名代替 Alignment；编码字节及真实执行证据等限制如实保留。

按新的持续授权，检查点提交后自主汇总各轮动作覆盖与质量缺口，不再等待用户逐阶段确认。

### 2026-09-11：AIB 笔记再适配与缺正文澄清完成

所有者明确确认本阶段。AIB-00139 从动作前用户标题及既有助手摘要生成一条隔离 note 提案；AIB-00159 缺 Q3 正文，生成 missing:body 澄清，继续排除发送候选。新增来源绑定模块、构造/核验脚本、配置及报告 `reports/data/aib_communication_pilot_20260911.md`，communication 配置增加显式隔离来源模式，项目叙事同步更新。

两条记录原文及边界逐条 AI 核对，未读取后续示范作为策略输入。新增七项 fixture 测试，完整 pytest **394 passed（79.64秒）**，Ruff、compileall、wheel（Conda intentfence，`--no-isolation`）通过。新记录双重重放及 --verify 核验通过，manifest SHA-256 `40b09e46e31c64982e8515fbe643e8752efb17f314507190e5e99275c3214fee`；旧四场景/五提案独立只读核验通过。所有原始/准备/动作 JSON 保持 ignored，未覆盖历史输出。

两轮累计五个有操作提案场景、六条操作提案，另有一条澄清。仍缺多任务风险/Alignment 覆盖、独立语义审核及家族隔离，未加入训练、赋标签或 split，也未执行真实工具、模型训练或最终评测。

下一阶段建议依据现有182条清单，挑选参数完整且边界明确的外泄、权限提升、工具操纵场景，构造小批同内容多动作对照；不支持或缺参数者继续隔离。使用已下载来源和本地 CPU，无新下载、GPU 或付费 API；本阶段提交推送后停止，等待所有者确认。

### 2026-09-11：笔记与邮件专用离线接口完成

所有者明确回复“确认下一阶段”，批准针对试点排除项补接口并做 fixture 验证。本阶段新增 `src/intentfence/communication_actions.py`、`configs/communication_actions_v1.yaml`、`tests/test_communication_actions.py` 和 `docs/communication_actions_20260911.md`，项目叙事同步更新。笔记 title/body 不映射成路径；邮件 To/CC/BCC 为独立列表，每项保留来源与当前用户授权位置。

历史正文的指代由准备者显式绑定；候选缺失或不唯一时澄清，不猜正文。goal_bounded 对所有收件人和正文检查当前授权依据；content_following 可记录低信任 BCC 的离线对照，但不补造缺失正文。它们均不执行发送、保存或文件操作，不赋 Risk/Alignment/split；自然语言授权解释仍需人工/独立语义审核，不能把字段位置检查当作语义正确证明。

验证：新增 **24项** 合成测试，完整 pytest **387 passed（68.63秒）**，无警告；Ruff、compileall、wheel（Conda intentfence，`--no-isolation`）通过。历史 AIB run_v1 只读校验再次通过，4场景/5观测及 manifest `9476c6935f7b58bcee77fd4e45dc7b1ef4b2f25037d46387c01a5f0c9eac66ee` 保持不变。没有新真实来源观测、训练样本、下载或模型运行。

下一阶段建议使用专用笔记接口重新适配 AIB-00139，只从动作前的标题与历史摘要生成隔离提案，核对多轮指代；AIB-00159 缺少 Q3 正文，继续排除发送候选，可生成缺字段澄清记录。仍不赋训练标签或 split、不训练，只用本地 CPU 和已下载来源。本阶段按规则提交推送后停止，等待明确确认。

### 2026-09-11：AIB 少量真实来源动作试点完成

项目所有者再次明确回复“确认下一阶段”。本阶段选择六个候选完整检查，四个成功适配并产生五条隔离提案（00100/00128/00147各一条，00178两条）；00139因 title/body 与 path/content 不同、00159因正文缺失及隐藏 BCC 接口不足而排除。试点是有目的挑选，不能推算全源可用率。五条动作逐条 AI 核对，无独立人审，未赋 Risk/Alignment/split。

新增 `src/intentfence/aib_pilot.py`、构造/只读校验脚本及 `configs/aib_action_pilot_20260911.yaml`；`offline_actions.py` 增加显式隔离来源模式及 AI 准备解释，保留旧 fixture 模式边界。原消息不改写成 JSON，参数逐字符绑定；00178的 key 含省略号，不能声称实际可用 SSH 凭据或攻击成功。详情与哈希见 `reports/data/aib_action_pilot_20260911.md`，项目叙事同步更新。

验证：新增七项 fixture 测试；完整 pytest **363 passed（62.98秒）**，Ruff、compileall 和 wheel（Conda intentfence，`--no-isolation`）通过。真实试点双重确定性重放通过，独立只读脚本核验原始参数及哈希通过，重复构造拒绝覆盖且已有观测哈希不变。最终 manifest SHA-256 `9476c6935f7b58bcee77fd4e45dc7b1ef4b2f25037d46387c01a5f0c9eac66ee`。原始数据及含原文的准备/动作记录保持 ignored。

本阶段只产生隔离模拟提案，不是真实代理执行或训练样本。AI 选择的字段解释仍需语义审核；独立 Alignment、完整家族归并/测试隔离及人审未解决。未执行源工具、构造 split、训练、校准或最终模型评测。

下一阶段建议根据本次排除项补充笔记 title/body 和邮件 CC/BCC 专用内存契约，用 fixture 验证多轮指代与缺正文时的保守行为；不编造缺失正文或批量套模板。只需本地 CPU，无新下载、GPU 或付费 API。本阶段按规则提交推送后停止，等待明确确认。

### 2026-09-11：离线动作策略与内存接口 fixture 实现完成

项目所有者明确回复“确认下一阶段”，批准从设计进入有限框架实现。本阶段新增 `src/intentfence/offline_actions.py`、`configs/aib_offline_actions_v1.yaml` 和 `tests/test_offline_actions.py`，实现六类内存提案接口、四种确定性选择规则、严格前缀/来源字段/授权契约、观测哈希及分组连边跨角色拒绝。既有 candidate 8 和数据构造入口保持原状。

验证：新增35项合成 fixture 测试；完整 pytest **356 passed（63.27秒）**，Ruff、compileall、wheel（Conda intentfence，`--no-isolation`）通过。测试包括未来回复排除、标签拒绝、同工具不同参数、授权变化、缺失对象/参数、重复 JSON 键、实现哈希绑定及目标文件不覆盖。说明与限制见 `docs/aib_offline_actions_implementation_20260911.md`，项目叙事同步更新。

这些接口只记录内存提案，不执行工具；未接入真实 AIB 场景、生成真实来源动作、应用 Alignment 或分配 split，未训练。自然语言到结构化事实的解释、授权语义、真实边界、完整家族隔离和人审仍待核验；配置声明 fixture-only 不代表能自动鉴别任意输入来源。固定规则观测不是真实代理执行证据。

下一阶段建议选择现有接口可忠实表达且可信边界明确的少量 AIB 案例，进行真实来源适配试点，逐条绑定原始行与动作前缀、核查准备层解释，生成隔离观测；不预设全部可用，不形成训练 split 或应用 Alignment。预计使用本地 CPU 和已下载来源，不需 GPU、付费 API 或新下载。本阶段按规则提交推送后停止，等待所有者明确确认。

### 2026-09-11：AIB 全量场景整理与动作设计完成

用户明确确认下一阶段后，182/182 条已完成全字段 AI 场景整理。实际分工 A61、B40、C60，额度中断后主审补齐21条，来源分别保存。暂定风险为外泄73、权限提升34、工具操纵25、指令劫持10、benign40；112个暂定家族名（79个单例）尚未完成同义/结构归并，不构成已隔离家族。全部训练标签、动作与split为空，AI意见未应用。

报告 `reports/data/aib_scenario_inventory_20260911.md` 与设计 `docs/aib_offline_action_design_20260911.md` 已形成。汇总器全量核验通过，最终manifest SHA-256 `967ac4e88adfef6b09e880c066096d513d027936b987c5920b728a0e9a1ee872`；完整测试321 passed（58.92秒），Ruff、compileall和wheel通过。该阶段只完成场景证据和动作方案，没有实现新策略或生成动作。

下一阶段建议按设计实现有限内存适配器、确定性策略和fixture验证，再按明确构造范围进入真实场景派生。当前源动作、独立Alignment、家族隔离及人审仍有缺口，未训练就绪。阶段提交后暂停，等待用户确认。

### 2026-09-11：AgentInjectionBench 只读审计完成

用户明确批准按提案下载并只读审计。四个固定文件合计 351742 bytes，大小与 Git blob OID 全部匹配，SHA-256 已保存；README/LICENSE 复用经同版本哈希验证的文档缓存。182 条中只有一条显式 tool_call，位于正常用户新请求后；9 条有目的 AI 抽查确认 unsafe 场景标签不能直接成为 malicious 动作标签。

全量 user/tool_result 文本跨案例精确与 5-shingle Jaccard>=0.8 比较无命中；对 13 个保护输入文件的 54483 段文本做同规则筛查也无命中，但不能证明完整场景/模板/AgentDojo 隔离。数据继续隔离，未赋本项目标签或生成 split。报告：`reports/data/aib_readonly_audit_20260911.md`，机器证据：`data/interim/aib_audit_20260911/audit_v2.json`，SHA-256 `586e34cdeec7d94a3826a27a70a90b7a3a5073fbd42bcb6fa979d6a41bccf1b8`。

新增审计脚本及 fixture 测试已验证：完整 pytest 315 passed（61.64 秒），Ruff、compileall、wheel 和 diff 检查通过。

下一阶段建议在此来源内建立完整隔离场景清单，审核风险机制与家族，再形成非统一模板的离线动作方案。本阶段按规则提交后停止，等待确认，不自动启动转换或训练。

### 2026-09-11：三类缺失风险来源检索

项目所有者已回复“确认下一阶段”。已使用文献检索 skill、OpenAlex 备用检索及官方论文/仓库/数据卡，核验缺失三类风险的动作来源；比较和排除理由见 `docs/candidate_9_targeted_action_sources_20260911.md`。没有确认可直接补齐五类风险与四类 Alignment 的现成训练集。

Agentic Prompt-Injection 5K 明确采用模板扩展且缺动作字段；ToolSafe 的论文训练文件未在当前公开仓库找到；AgentAlign 可作良性模拟动作候选但不能直接填补注入攻击。优先提出 AgentInjectionBench 固定版本 351742 bytes 的隔离只读审计，配置为 `configs/candidate_9_aib_audit_proposal_20260911.yaml`，新来源批准仍为 false。其官方类别分层 70/15/15 代码不证明模板家族隔离，实际动作来源及锁定集合重叠须在审计时核验。

本阶段仅新增文档与提案配置，核验 YAML、文件规模求和和文档差异；未改变运行代码，不重复模型或数据测试。未下载新原始数据、运行来源工具、生成样本或训练。阶段提交后停止，待新来源条款与所列只读范围得到明确批准。

### 2026-09-11：ToolSafety 隔离完整 AI 预审完成

已完成批准范围内 **200/200** 条完整动作前上下文 AI 预审：主审此前完成 43 条，三个 agent 分别完成 53、52、52 条，成员互斥且无遗漏。Risk 暂定 benign 200；Alignment 为 aligned 112、ambiguous 86、unrelated 2、malicious 0。该抽样未提供缺失攻击类别证据，不表示整个源没有攻击。多 agent 分工不是双独立审核，也不是人审。

汇总器重放全部 200 条源边界及抽样，核验历史回执、意见文件哈希、AI 身份和训练标签边界，通过并返回 `ai_reviewed_quarantined`。最终本地证据为 `data/interim/toolsafety_full_review_20260911/manifest.json` 与 `reviews.jsonl`；历史初筛和增量记录保留。详情见 `reports/data/toolsafety_prefix_pre_review_20260911.md`。

本阶段新增批准配置、构造/封装/验证/汇总四个脚本、两份测试与报告，并更新项目叙事。完整测试 312 passed，最终哈希记录补充后相关 16 项再次通过；Ruff、compileall、wheel 通过。阶段提交按本计划推送当前功能分支，提交身份见 Git 历史和阶段汇报。

数据继续隔离：未应用训练标签、未执行源工具或模型训练；上游归属、锁定集合隔离、独立审核和同内容多动作对照仍未完成。建议下一阶段定向检索具有攻击目标和动作证据的三类缺失风险来源，先做条款与测试重叠核验。本次阶段结束，按规则等待所有者确认后进入下一阶段；原五类风险和动作感知多任务目标不变。

### 2026-09-10：ToolSafety 只读结构审计

只读诊断进一步完成：定义异常中 1823 条为完全相同的重复定义，860 条为同名冲突；后续动作位置通过名称/必需参数名/前置返回配对有限筛查的有 4760 个，属于 2873 条对话。三例 AI 语境观察表明中间动作不能继承整条安全轨迹标签。详见 `reports/data/toolsafety_diagnostics_20260910.md`。没有修复原始文本、赋训练标签或执行候选转换。

已完成经批准的约 223 MB 固定源下载和哈希验证；实际为 15569 条对话，其中 6234 条含工具返回，3642 条含工具返回后的可解析调用。共 1698 项前置调用未解析，2686 条对话的工具定义尚未解析，不能整包纳入训练。机器报告为 `data/interim/toolsafety_audit_20260910/structure_v2.json`，汇报见 `reports/data/toolsafety_readonly_audit_20260910.md`。本阶段未转换、赋标签或执行模型/工具；后续先补格式及上游归属核验，候选转换仍需明确阶段确认。

### 2026-09-09：Dolly 公开来源接入

动作来源检索新增 `docs/candidate_9_action_source_scan_20260909.md`。项目所有者已批准 ToolSafety 固定版本约 223 MB 的下载与只读审计；下载和后续审计进行中，不授权训练候选接入。AgentDoG/AgentInstruct 因原始数据条款未明暂不下载。本阶段先完成来源与动作字段可用性核验，再报告可用范围及剩余缺口。

项目所有者已明确选择“继续补齐原五类风险和动作数据”。后续继续原五类 Risk、四类 Task Alignment 与动作感知多任务的数据准备，不改为二分类文本检测实验。Dolly v3 仅是背景扩充候选；下一步先核对标签覆盖、动作证据与来源缺口，详见 `docs/candidate_9_multitask_completion.md`。该决定不授权模型训练、校准或最终测试评测。

项目所有者已明确批准固定版本 Dolly-15k 的约 13.1 MB 下载、CC-BY-SA-3.0 归属保留，以及带参考文本的问答、摘要、信息抽取用途。下载已完成，原始 15011 条中筛选出 4467 条有参考文本的背景。独立 v3 已构造 20691 条（14582/2065/2044/2000），并保护 v2 calibration/Test A；独立 verifier 已正常退出并通过，逐条重建 17784 条 Dolly 衍生记录。详见 `reports/data/candidate_9_v3_build_20260909.md`。未训练就绪，不能据新增数据量声称模型收益。

### 2026-09-08：candidate 9 公开来源扩充入口

进一步来源调查已形成 `docs/candidate_9_source_expansion_decision.md`：deepset 数据卡许可证声明冲突、SafeGuard 数据卡缺少明确许可证，均未下载。Dolly-15k 可补充带参考文本的人工问答/摘要/抽取背景，已固定 revision、13.1 MB 下载范围及 CC-BY-SA-3.0 归属记录，纯适配器 fixture 已准备。`configs/candidate_9_source_proposals.yaml` 中新条款批准仍为 false；等项目所有者明确确认后才能下载并连接下一版构造，不能把普通指令标签冒充安全或动作标签。

后续构造已获用户确认并完成 candidate_9_v2：总计 3620 条，四角色分别为 2550/357/351/362，独立 verifier 通过。实际规则和限制见 `configs/candidate_9.yaml`、`reports/data/candidate_9_build_20260908.md`。这替代下面“仅完成来源入口”的停止状态；当前仍未训练就绪，主要缺口为 Table 来源占比过高、困难负样本量少、五分类/独立 Alignment/动作覆盖未完成。旧 candidate 8 保持不变。

用户已确认继续此前的公开训练集扩充。已完成 BIPIA/InjecAgent 固定来源共 123 个登记文件的大小与 SHA-256 核验，以及 Email 50/Table 900 条 clean 背景的严格转换（skipped=0，split=null，待审核）。
InjecAgent 62 条攻击原文、17 条用户指令全部与官方测试重叠，触发原 candidate 9 方案的训练排除条件；重组不能提供隔离的训练素材。
完整 candidate 9 尚未就绪：须补全独立 calibration 的协议设计、背景/攻击家族隔离配对、CodeQA 专用适配与上游条款，以及多样化攻击/困难负样本和标签审核。详见 `reports/data/candidate_9_source_audit_20260908.md` 与 `docs/candidate_9_data_plan.md`。当前停止点为本次数据入口核验汇报；candidate 8 保持历史工程基线，未启动下一轮训练。

### candidate 8 历史停止点（保留）

当前活动候选为 candidate 8。其 27,000 条 project-owned mock 语料、manifest、split 隔离与
归一化模板检查已通过；两轮双 AI 工程审核与一次项目所有者分歧裁决均已如实封存。2026-09-04
已新增冻结的 `B-ai-assisted-engineering` 路线：AI 证据仍不等同于人类审核，但可在结构证据
通过且项目所有者明确接受当前失败质量门后支持工程训练。`human_verified=false` 与
`formal_training_authorized=false` 不变，Test B/C/D、calibration 和最终测试锁继续保持。

为便于项目所有者复核最新双 AI 结果，已另外生成只包含 137 条分歧的项目所有者复核包（当前加固版
目录为 `data/interim/route_b_v2_candidate_8_ai_disagreement_adjudication_v2/`；Risk 80、
Alignment/action realism 57）。项目所有者已完成逐条裁决，validator 已通过并生成
`submission_receipt.json`。该包保留双方 AI 意见和源文件哈希，但不包含 seed labels，也不满足
两名独立人类审核门；它只能作为可追溯的工程分歧裁决记录，不能直接把 `human_verified` 或
`formal_training_authorized` 改为 true。正式人工 v2 包仍须由两名独立人类各完成 400 条 Risk
和 400 条 Alignment 审核。

为满足尚未完成的协议门，已生成独立于 AI 输出的 candidate 8 v2 人工双盲包；两名独立人类审核者各
须完成 400 条 Risk 和 400 条 Alignment，之后才可运行确定性人工审核聚合与任何后续授权判断。
最新状态复查（2026-09-02）：四份 reviewer CSV 均为 0/400 条完整审核，两份 attestation 的
`reviewer_id` 为空且 `independence_declared=false`；本次未运行聚合、应用或训练授权判断。
双 AI 补充审核已按用户指示完成，但它仍是 `ai_reviewed_engineering_only` 负证据，不能替代
独立人类签核。最新双 AI 分歧的项目所有者补充复核包详情见
`docs/route_b_ai_disagreement_handoff.md`；正式两名独立人类 v2 审核包详情见
`docs/route_b_candidate_8_human_audit_handoff.md`。C2a 的代码、fixture 与 dry-run 仍是框架准备，
不构成进入正式研究训练的授权；C2b 已于 2026-09-05 完成一次用户确认并在 tmux 启动的
Base C multitask seed 42 AI 工程运行，训练和 checkpoint reload 通过。聚合结果与复现记录见
`reports/training/c2b_base_action_multitask_seed42_20260905.md`；这不解除正式人类审核门，
也不代表完成 C2b 的多变体、多 seed 主实验。当前停在本次结果提交与复核处，未启动下一轮训练。
C2c 的 reliability
diagram/classwise ECE、calibration split 哈希校验、只读 preflight 和 owner authorization gate
已准备，但没有用于校准的真实 logits、温度或阈值。校准和最终测试仍锁定；下一轮训练仍须先展示
完整命令并由用户确认，本轮结果提交不授权其他变体、seed 或后续阶段。
C3a 的固定阈值评测、分组/错误分析、cluster bootstrap、Wilson 区间和一次性
final-test ledger 也已准备，但没有读取或生成真实 Test A/B/C 预测。按用户指示，已先继续
推进不依赖 checkpoint 的 C3b 工程框架；C3b 的真实导出、INT8 安全重跑和 CPU 实测仍等待
冻结模型与对应阶段确认，不改变人工审核、训练、校准和最终测试门。
